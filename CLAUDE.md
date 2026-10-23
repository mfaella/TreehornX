# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

TreehornX is a research prototype that verifies memory safety of C programs manipulating trees and lists. It implements
the knitted-tree / CHC method of Faella & Parlato, *Verifying Tree-Manipulating Programs via CHCs* (CAV25, extended
version in `notes/`), and adds **preconditions** expressed as symbolic data-tree automata (SDTAs). Postconditions are
the next goal but are **not implemented** (an earlier DFS engine and post CHC were removed in `a3e6307`).

## Commands

Dependencies are managed with `uv`. The project runs on PyPy 3.11 (`.python-version`), so code must stay 3.11-compatible:
no PEP 695 generics/`type` aliases, `override` comes from `typing_extensions`. There is no SMT library dependency:
terms and clauses are the in-house `chc/smt` package and solvers run as external processes.

```bash
uv sync                                   # install
uv run task format                        # ruff format + isort
uv run task validate                      # isort/ruff checks + pyright (strict mode)
uv run task test                          # pytest over tests/
uv run task verify                        # format + validate + coverage (what CI runs, 85% branch coverage)

uv run pytest tests/integration/test_lab_chc.py -k sll_safe_find   # single case
uv run pytest -m "not slow"                                         # skip verification runs taking minutes

uv run treehornx verify FILE.c --pre bst -m 1 -n 128 --check-sat         # CLI (Z3 by default, --eldarica)
uv run treehornx verify FILE.c --smt2                                   # dump one SMT-LIB2 system per exit status
uv run python scripts/benchmarks.py [--only SUBSTR] [--timeout S] [--out FILE.csv]
```

- Integration tests call the `z3`/`eld` binaries and are skipped when they are not found. Solver binaries are shipped
  under `scripts/solvers/linux/x86-64/` (z3) and `tests/integration/solvers/` (eld); the CLI takes `--solvers-dir`
  and falls back to `PATH`. (The golem binaries there are no longer used.)
- Terms carry their own types and predicates their own signatures, so several systems can be built in one process
  without resetting any environment. Terms are hash-consed in a weak cache (identity equality); `sx.reset_env()`
  empties it, after which older terms are no longer equal to new ones.
- `docs/replicating_benchmarks.md` explains how to reproduce the paper benchmarks (they were produced on the `post`
  branch).

## Pipeline

`main.py` (Typer CLI, output helpers in `tui.py`) runs:

1. **Parse** — `parser.py` lowers a restricted C subset (one `struct`, one `void f(struct NODE *root)`, top-level
   declarations, at most one dereference per statement, no field access inside expressions/conditions) via
   pycparser into `ir.py`. The IR mirrors Sec. 2 of the paper: pointer vars, data vars, pointer fields and data
   fields are four separately-numbered namespaces; the root is pointer var 0; the only branch is `IfGoto`.
   Uninitialised data vars are inputs (nondeterministic), pointer vars are nil.
2. **Enumerate the shape** — `enum_models/Lab/LabEngine.py` (on top of the generic worklist fixpoint in
   `enum_models/core/SymbolicEngine.py`) computes every *label* (a node's log of frames) and every *pair*
   (parent label, child label, child index j) reachable within bounds m (allocations) and n (frames per label).
   Initial labels/pairs come from `Lab/initial.py` (CHC I/II), step predicates of Appendix C are methods
   `step_*_{int,ext,down}`, auxiliary predicates (`points_here`, `stop_rewind`, `rewind_target`, …) live in
   `Lab/helpers.py`.
3. **Build CHCs over data only** — `chc/Lab/system.py::build_lab` turns enumerated labels into one predicate per
   label (`Lab<id>`) whose arguments are only the data symbols (`v<id>_<frame>`, `f<id>_<frame>`;
   `chc/Lab/symbols.py`). `chc/Lab/clauses.py` emits facts (CHC I/II), internal clauses (CHC III) and external
   clauses (CHC IV/V), plus one query per label ending with the checked exit status.
4. **Precondition layer (optional, `--pre`)** — `chc/pre/runner.py::BotUpAutomataRunner` attaches a companion
   predicate `Pre<id>` to every label and runs the SDTA bottom-up over the backbone pairs (POPL-style, Fig. 4),
   carrying an error flag `e` up to the root. `chc/pre/PreRunner.py` binds it to Lab labels. Available automata are
   in `chc/sdta/SDTAContext.py` + `psi.py` (`bst`, `bst_strict`, `sll_sorted`, `sll_sorted_strict`, `avl`, `rb`).
   The ψ functions hard-code the field names (`next`, `left`, `right`, `data`), so input programs must use them.
5. **Solve** — `chc/smt/sexpr.py` holds the terms (`Var`, `Constant`, `OpExpr`, `Application`, `Clause`, whose
   constructors return the cached instance from one weak cache per class; operators are built as
   `sx.OpExpr(sx.Operator.X, ...)`, `sx.Max` builds the `ite` chain) and `CHCSystem`, which prints a `HORN` script declaring only the predicates used;
   `chc/smt/preprocess.py` has `substitute`/`simplify`/`fresh_var` (used by `clean.py`). `chc/solvers` pipes the
   script into `z3 -in` (`Z3Solver`) or `eld -in` (`EldaricaSolver`) and returns `Status` SAT/UNSAT/UNKNOWN.
   **sat = safe, unsat = an error is reachable.** One system is built per exit status (ERR, OOM, LABEL_OVERFLOW)
   that the enumeration actually reaches; unreached ones are reported as "trivially" safe without calling a solver.

`feature_flags.py::FeatureFlags` (CLI: `--clean-clause`, `--lab-internal-constraints`, `--pre-internal-constraints`): `clean_clause` (merge variables equated in a clause body, `chc/clean.py`; clauses are built uncleaned and cleaned lazily one at a time when printed, via `CHCSystem.transform`/`write_smt2(..., clean)`),
`lab_internal_constraints` / `pre_internal_constraints` (repeat the constraints of every internal step
of a label in each clause instead of only the step to its top frame). They change the size/shape of the systems, not
their meaning; all default to off. `LabCHC` and `BotUpAutomataRunner` carry the flags, helpers needing one take a bool.

Conventions: positions inside a label are **1-based** like the paper (`sigma[1]` is the first frame,
`sigma[len(sigma)]` the top one); `σ`/`τ` naming follows the paper (σ sends the lace, τ receives the new frame). Child
indices `j` are 0-based, auxiliary (allocation) children are `j ∈ [k, k+m)`. In external clauses σ's symbols are
prefixed `s`, τ's `t`; in Pre clauses the parent's `p_`, children's `c<j>_`.

## How the implementation differs from CAV25

The paper defines a *single* predicate `Lab(σ)` over the full data signature and lets the CHC solver discover
everything. The implementation follows the paper's "Efficient Implementation" future-work idea instead:

- **Shape is enumerated, data is solved.** All finite-domain frame fields (`active`, `pc`, `upd`, `isnil`, `event`,
  `active_child`, `prev`, `next`) are computed explicitly in Python; only data variables and data fields go to the
  solver. Each enumerated label gets its own predicate (case splitting), so `Ψ_Internal/Ψ_Up/Ψ_Down` reduce to
  equalities over data symbols.
- **Labels have no `avail` / fixed length n+1.** A label is an immutable linked list of frames (`core/Label.py`,
  prefix + top frame, hash-consed), so `len(σ, i)` and the `σ^{<i}` shorthand become `label.prefix` / `label.cut(i)`.
- **`prev`/`next` store only a direction** (`Up | Internal | Down(j)`, `core/Dir.py`), not `Dir × index`. The linked
  frame is recovered by counting (`down_links`/`up_links`/`linked_frames` in `helpers.py`), which is sound because a
  frame either steps internally or sends the lace out, never both.
- **`next` is predicted, not guessed.** The paper leaves `next` nondeterministic until the following frame fixes it;
  here `next_dir.py::predict_next_dir` computes it when the frame is created, and every `step_*` takes it as
  `expected_next_dir` and only tries the matching case. "Leadership" checks on pairs (`parent_leadership`,
  `child_leadership`) replace the paper's `consistent_child` check; `LabEngine.consistent` always returns True.
- **Data conditions are not evaluated during enumeration.** `if (data-cond)` takes both branches
  (`step_local_branch_int`) and the CHC clause adds the guard; `d := e`, `p->df := x`, `x := p->df` only advance the
  pc in the shape and are expressed in `psi_internal`.
- **Internal-chain compression.** Frames strictly inside a chain of internal steps are dropped from the predicate's
  arguments (`ChcLabUtils.kept_frames`), and CHC III is emitted only for kept prefixes. With the internal-constraints
  flags off, a clause only constrains the step to its head's top frame.
- **Only labels that can reach the end of a lace are kept** (`SymbolicEngine.finals`), and queries are issued per
  label instead of the single `label_exit(σ, Ex)` query CHC VI.
- **Event set extended** (`Lab/Event.py`, rationale in `FORMULAS_UPDATES.md`, in Italian): `FieldHere(pfield)`
  (⟨pfield := here⟩) disambiguates `p->pfield := q` when q already points to the current node; `LOF` marks label
  overflow; `Rewind(i)`/`RwdSpec(i, p)` are the paper's `rwd_i`/`rwd_{i,p}`. `step_assgn_to_field`,
  `is_pfield_*` and `step_assgn_from_field` follow the corrected formulas there (including setting `isnil_p = false`
  when `p := q->pfield` moves down to an implicit child, where the paper would copy the default).
- **Data model.** The paper assumes a single data field `val : D`; the IR supports any number of `int`/`bool` data
  fields and variables. `bool` heap conditions (`b = (p == q)`) and `p->pf == NULL` tests are first-class
  statements rather than being reduced to `p = q` via auxiliary variables.
- **No MemSafety loop.** The CLI checks one `(m, n)` (defaults m=0, n=128 — far above the paper's typical n ≤ 10)
  and reports each exit status separately; it does not increment m/n. Flags `-c`, `--partial-correctness`,
  `--interactive-check-sat`, `--parent` and the dependency-graph options are accepted but ignored.
- **Preconditions** (beyond CAV25, sketched in its Sec. 7): the SDTA reads only the first frame of each input node
  (`is_input_node` = `label[1].active`); non-input/auxiliary nodes get the nil state; the query fires when the root's
  state is accepting (`psiF`) and the propagated error flag is true. An empty input tree is accepted by default
  (`accept_empty`).

## Repository notes

- `notes/predicates.md` (+ `notes/rsc/*.png`) is the reference list of the paper's predicates/formulas the engine
  implements; consult it alongside the PDF when touching a `step_*` method.
- `enum_models/__init__.py` (`KnittedTrees`, `generate_labels`) is a legacy wrapper whose `LabEngine(...)` call no
  longer matches the constructor; the live entry point is `chc/Lab/system.py::build_lab`.
- The repo root contains large generated artifacts (`*.smt2`, `*.log`, `prolog.horn`, `smt/`, `.profile/`); don't read
  them whole and don't commit them.
