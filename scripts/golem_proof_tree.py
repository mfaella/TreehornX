#!/usr/bin/env python3
"""
golem_proof_tree.py

Run the Golem CHC solver on a CHC system with

    golem --engine spacer --print-witness <file.smt2>

and, when the system is UNSAT, render the refutation proof (the derivation of
`false`) as a Graphviz tree, written to an SVG file.

Golem's default ("legacy") witness format prints one line per derivation step:

    <index>:\t<derived-fact> -> <premise-index> <premise-index> ...

Each step is a ground instance of a clause: the premises are facts derived in
earlier steps, the derived fact is the conclusion. The step that derives
`false` is the root of the refutation; steps with no premises are base facts.
We build a directed graph with an edge  step -> premise  for every premise, so
the tree reads top-down from `false` to the base facts.

Usage:
    python3 golem_proof_tree.py system.smt2
    python3 golem_proof_tree.py system.smt2 -o proof.svg
    python3 golem_proof_tree.py system.smt2 --golem /path/to/golem --engine spacer

    # Parse an already-captured witness instead of invoking Golem:
    python3 golem_proof_tree.py --from-output witness.txt -o proof.svg
"""

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import graphviz
except ImportError:
    sys.exit("The 'graphviz' Python package is required: pip install graphviz "
             "(and the system 'dot' binary from the graphviz package).")


# A derivation step line looks like:  "3:\t(inv 2) ->  1 2"   or   "0:\ttrue"
# We split on the literal " -> " separator that Golem prints between the
# derived fact and its premise indices.
_STEP_RE = re.compile(r"^\s*(\d+)\s*:\s*(.*)$")
_PREMISE_SEP = " -> "


@dataclass
class Step:
    index: int
    fact: str
    premises: list = field(default_factory=list)


def parse_witness(text: str):
    """Parse Golem's legacy UNSAT witness into a list of Step objects.

    Returns (answer, steps) where answer is 'unsat' / 'sat' / 'unknown' / None
    and steps is the list of derivation steps (empty unless answer == 'unsat').
    """
    answer = None
    steps = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped in ("sat", "unsat", "unknown") and answer is None:
            answer = stripped
            continue
        m = _STEP_RE.match(line)
        if not m:
            continue
        index = int(m.group(1))
        rest = m.group(2)
        if _PREMISE_SEP in rest:
            fact_part, premise_part = rest.split(_PREMISE_SEP, 1)
            premises = [int(tok) for tok in premise_part.split()]
        else:
            fact_part, premises = rest, []
        steps.append(Step(index=index, fact=fact_part.strip(), premises=premises))

    # If we never saw an explicit answer line but parsed steps, assume unsat.
    if answer is None and steps:
        answer = "unsat"
    return answer, steps


def run_golem(golem_bin: str, chc_file: str, engine: str) -> str:
    """Invoke Golem and return its combined stdout."""
    if shutil.which(golem_bin) is None and not Path(golem_bin).exists():
        sys.exit(f"Golem binary not found: '{golem_bin}'. "
                 f"Pass --golem /path/to/golem or put it on your PATH.")
    cmd = [golem_bin, "--engine", engine, "--print-witness", chc_file]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        sys.exit(f"Failed to execute Golem: {e}")
    if proc.returncode != 0 and not proc.stdout.strip():
        sys.exit(f"Golem exited with code {proc.returncode}.\n{proc.stderr}")
    return proc.stdout


def _short(label: str, limit: int = 60) -> str:
    label = label.strip()
    return label if len(label) <= limit else label[: limit - 1] + "\u2026"


def build_graph(steps, title: str | None = None) -> "graphviz.Digraph":
    """Build a Graphviz Digraph of the refutation proof tree."""
    by_index = {s.index: s for s in steps}
    # Premises are the children; a step that is nobody's premise is a root.
    referenced = {p for s in steps for p in s.premises}
    leaf_indices = {s.index for s in steps if not s.premises}

    dot = graphviz.Digraph("refutation", format="svg")
    dot.attr(rankdir="TB", splines="true", nodesep="0.35", ranksep="0.55")
    dot.attr("node", shape="box", style="rounded,filled", fontname="Helvetica",
             fontsize="11", color="#888888")
    dot.attr("edge", color="#555555", arrowsize="0.7")
    if title:
        dot.attr(label=title, labelloc="t", fontsize="14", fontname="Helvetica")

    for s in steps:
        is_false = s.fact.strip().lower() == "false"
        is_root = s.index not in referenced or is_false
        is_leaf = s.index in leaf_indices

        if is_false:
            fill, border = "#f8d7da", "#c0392b"   # red: the derived contradiction
        elif is_leaf:
            fill, border = "#d5f5e3", "#1e8449"   # green: base facts
        elif is_root:
            fill, border = "#fdebd0", "#d68910"   # orange: a top conclusion
        else:
            fill, border = "#d6eaf8", "#2471a3"   # blue: intermediate facts

        label = f"#{s.index}\\n{_short(s.fact)}"
        dot.node(str(s.index), label=label, fillcolor=fill, color=border)

    # Edge: conclusion -> each premise it was derived from.
    for s in steps:
        for p in s.premises:
            if p in by_index:
                dot.edge(str(s.index), str(p))
    return dot


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run Golem (spacer) on a CHC system and render the "
                    "refutation proof tree as SVG.")
    ap.add_argument("chc_file", nargs="?",
                    help="Input CHC system (.smt2). Omit if using --from-output.")
    ap.add_argument("-o", "--output", help="Output SVG path "
                    "(default: <chc_file>.svg or proof.svg).")
    ap.add_argument("--golem", default="golem", help="Golem binary (default: golem).")
    ap.add_argument("--engine", default="spacer", help="Golem engine (default: spacer).")
    ap.add_argument("--from-output", metavar="FILE",
                    help="Parse this captured Golem witness instead of running Golem.")
    ap.add_argument("--keep-dot", action="store_true",
                    help="Also keep the intermediate Graphviz .dot source.")
    args = ap.parse_args(argv)

    if args.from_output:
        text = Path(args.from_output).read_text()
        base = args.chc_file or args.from_output
    elif args.chc_file:
        text = run_golem(args.golem, args.chc_file, args.engine)
        base = args.chc_file
    else:
        ap.error("Provide a CHC file, or --from-output FILE.")

    answer, steps = parse_witness(text)

    if answer == "sat":
        sys.exit("Golem reports the system is SAT (no refutation exists). "
                 "A refutation proof tree is only produced for UNSAT systems.")
    if answer == "unknown":
        sys.exit("Golem returned 'unknown' \u2013 no refutation proof to draw.")
    if not steps:
        sys.exit("No derivation steps found in Golem's output. "
                 "Make sure it was run with --print-witness and the result is unsat.\n"
                 "--- Golem output was ---\n" + text)

    out = Path(args.output) if args.output else Path(base).with_suffix(".svg")
    title = f"Golem refutation proof  ({Path(base).name}, engine={args.engine})"
    dot = build_graph(steps, title=title)

    # graphviz.render writes <stem> + .svg; we control the stem ourselves.
    svg_bytes = dot.pipe(format="svg")
    out.write_bytes(svg_bytes)
    if args.keep_dot:
        Path(out).with_suffix(".dot").write_text(dot.source)

    root = next((s for s in steps if s.fact.strip().lower() == "false"), steps[-1])
    print(f"Parsed {len(steps)} derivation steps (root: step #{root.index} -> "
          f"{root.fact.strip()}).")
    print(f"Wrote proof tree: {out}")


if __name__ == "__main__":
    main()
