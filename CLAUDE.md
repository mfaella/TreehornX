# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

TreehornX is a research prototype that verifies memory safety of C programs manipulating trees and lists. It implements
the knitted-tree / CHC method of Faella & Parlato, *Verifying Tree-Manipulating Programs via CHCs* (CAV25, extended
version in `notes/`), and adds **preconditions** expressed as symbolic data-tree automata (SDTAs) and the
**tree-shape check** of the output heap (tainting, Sec. 6 of the POPL27 draft in `notes/`). Custom postconditions
(Sec. 7, the S predicate over output states) are **not implemented** yet.

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

uv run treehornx verify FILE.c --pre bst -m 1 -n 128 --check-sat         # CLI (Z3 by default, --eldarica, --golem, --portfolio)
uv run treehornx verify FILE.c --smt2                                   # dump one SMT-LIB2 system per exit status
uv run treehornx verify FILE.c --tree-shape --pre bst --check-sat       # also check that the output heap is a tree
uv run python scripts/benchmarks.py [--only SUBSTR] [--timeout S] [--out FILE.csv]
```

- Integration tests call the `z3`/`eld` binaries and are skipped when they are not found. Solver binaries are shipped
  under `scripts/solvers/linux/x86-64/` (z3, golem) and `tests/integration/solvers/` (eld, golem); the CLI takes
  `--solvers-dir` and falls back to `PATH`. `PortfolioSolver` writes the system to a temporary file and races golem,
  z3 and eldarica on it (first sat/unsat wins, the others' process groups are killed); golem has no timeout flag, so
  it is killed when the timeout expires.
- Terms carry their own types and predicates their own signatures, so several systems can be built in one process
  without resetting any environment. Terms are hash-consed in a weak cache (identity equality); `sx.reset_env()`
  empties it, after which older terms are no longer equal to new ones.
- `docs/replicating_benchmarks.md` explains how to reproduce the paper benchmarks (they were produced on the `post`
  branch).
- Tree-shape tests: `tests/integration/test_tree_shape.py` (`*_shape_*` programs, each also checked memory safe;
  safe cases also assert that `finals()` has a root, so SAT is not vacuous), `test_tree_shape_pre.py` (`*_pre_shape_*`
  programs whose verdict depends on the precondition), `test_post_chc.py` (the memory cases through the Post system),
  `test_cli_tree_shape.py`; unit tests in `tests/unit/enum_models/test_taint.py` (including completeness of
  `finals()` against per-tree fixpoints) and `test_shape.py`. `TestConfig.layer = "post"` selects `Post.make_system`.

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
3. **Data constraints** — `chc/Lab/system.py::build_lab` keeps the final labels and pairs; the data of a label are
   the symbols `v<id>_<frame>`, `f<id>_<frame>` of its kept frames (`chc/Lab/symbols.py`). `chc/Lab/clauses.py`
   has no clauses any more, only constraint builders: `label_constraints` (every step reaching a frame of the
   label: ψ_internal for internal steps, the field copy from the frame below for external steps, CHC II for the
   root) and `consistency_constraint` (data variables equal on the frames of a parent and child linked in the lace).
4. **Bottom-up automaton (the whole system)** — `chc/pre/runner.py::BotUpAutomataRunner` attaches a predicate
   `Pre<id>` to every label and runs an SDTA bottom-up over the backbone pairs (POPL-style, Fig. 4), carrying an
   error flag `e` up to the root. Its clauses carry `label_constraints` of every node and the consistency with its
   children, so there are no Lab predicates and no clauses for the steps of the lace. The children of a node are
   collected one at a time, not over their product: `Pre<id>_<N>` holds the node's data, the states of the first N
   children that ψ reads (input pointer children, decided by `is_input_child(parent, j)`) and the error flag
   accumulated so far (`pre_p_e<N>`); `Pre<id>` follows from `Pre<id>_<k+m>` through ψ. `chc/pre/PreRunner.py` binds
   it to Lab labels. Without `--pre` the trivial automaton `true_ctx()` (no states, ψ = ψ_F = true) is used.
   Automata are in `chc/sdta/SDTAContext.py` + `psi.py` (`bst`, `bst_strict`, `sll_sorted`, `sll_sorted_strict`,
   `avl`, `rb`). The ψ functions hard-code the field names (`next`, `left`, `right`, `data`), so input programs
   must use them.
5. **Solve** — `chc/smt/sexpr.py` holds the terms (`Var`, `Constant`, `OpExpr`, `Application`, `Clause`, whose
   constructors return the cached instance from one weak cache per class; operators are built as
   `sx.OpExpr(sx.Operator.X, ...)`, `sx.Max` builds the `ite` chain) and `CHCSystem`, which prints a `HORN` script declaring only the predicates used;
   `chc/smt/preprocess.py` has `substitute`/`simplify`/`fresh_var` (used by `clean.py`). `chc/solvers` pipes the
   script into `z3 -in` (`Z3Solver`) or `eld -in` (`EldaricaSolver`) and returns `Status` SAT/UNSAT/UNKNOWN.
   **sat = safe, unsat = an error is reachable.** One system is built per exit status (ERR, OOM, LABEL_OVERFLOW)
   that the enumeration actually reaches; unreached ones are reported as "trivially" safe without calling a solver.
6. **Tree shape (`--tree-shape`, check `TREE_SHAPE`)** — runs after the memory checks and assumes they hold (the
   paper's composition assumption; shape errors are not filtered by exit status). Steps:
   - `enum_models/Taint/TaintingEngine.py` (a `SymbolicEngine[TaintedLabel]`) lifts the final Lab labels/pairs to
     `TaintedLabel(taint_node, taint_ptr, lab)` and saturates Rules 1–5 of POPL27 Fig. 5: `step_int` = T5 (a trail
     ending on the node, via `points_here`, taints it) + T3 (a tainted node seeds a ⊤ trail at the last
     ⟨pf := p⟩ of each field), `step_down` = T2 (structural child) + T4 down, `step_up` = T4 up; T1 seeds
     `taint_ptr[(ROOT, last frame)] = ⊤+` on the end-of-lace label at initialisation. Taints are `BoolPlus`
     (⊥ < ⊤ < ⊤+, merged by join; hashed by value so the systems come out in a fixed order); `TaintPtr` stores only
     non-⊥ keys `(p, frame)`. A step returns None when nothing changes.
   - `finals()` (`Taint/finals.py::saturated_finals`) keeps the saturated labels (`is_saturated_l`) and pairs
     (`is_saturated_p`) that compose a tree: a greatest fixpoint by removal with per-(label, j) support counters
     (an unvisited input tail is a label paired with itself, so revisits must count as true), then a BFS from the
     `is_initial` roots. It over-approximates: each child slot is satisfied independently.
   - `Taint/shape.py` reads the violations off the taints (`ShapeError`, POPL27 Fig. 9): `label_errors` (two trails
     ending on a node, a trail ending on a freed node, trails merging, a self-loop) and `pair_errors` (a trail
     landing on a seed, a structural child that is also a trail end or was freed).
   - `chc/Post/` mirrors `chc/Lab` + `chc/pre`: `post_from_lab`/`build_post` (taints on top of `build_lab`),
     `TreeShapeRunner` (a `BotUpAutomataRunner[TaintedLabel]`, predicates `Post<id>`, Lab data constraints on
     `state.lab`, `is_error` = shape errors of the label (+ `exit_codes`, empty by default), `is_pair_error` = shape
     errors of the pair), `tree_shape_clauses`, `make_system`. The precondition works as in step 4.

   `BotUpAutomataRunner` is generic over the node state `NS` (`PreRunner` is `[Lab]`). Its `is_pair_error(parent,
   child, j, ...)` hook (false by default) is ORed into the parent's accumulated flag in `collect_clause`, so pair
   errors reach the root query like node errors; there is no separate per-pair query.

`feature_flags.py::FeatureFlags` (CLI: `--clean-clause`): `clean_clause` (merge variables equated in a clause body,
`chc/clean.py`; clauses are built uncleaned and cleaned lazily one at a time when printed, via
`CHCSystem.transform`/`write_smt2(..., clean)`). It changes the size/shape of the systems, not their meaning, and
defaults to off.

Conventions: positions inside a label are **1-based** like the paper (`sigma[1]` is the first frame,
`sigma[len(sigma)]` the top one); `σ`/`τ` naming follows the paper (σ sends the lace, τ receives the new frame). Child
indices `j` are 0-based, auxiliary (allocation) children are `j ∈ [k, k+m)`. In clauses the parent's symbols are
prefixed `p_`, the children's `c<j>_`.

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
- **No clauses for the steps of the lace.** CHC I–V are not emitted: the steps of a label become its
  `label_constraints`, the links between nodes the consistency constraints, and both are conjoined in the
  bottom-up automaton clauses over complete backbone trees. Frames strictly inside a chain of internal steps are
  dropped from the predicate's arguments (`ChcLabUtils.kept_frames`) and only occur as quantified variables.
- **Only labels that can reach the end of a lace are kept** (`SymbolicEngine.finals`), and the query CHC VI is
  issued on the root of the automaton run (with the trivial automaton when there is no precondition).
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
- **Tainting** (POPL27 Sec. 6, which defines it as CHCs C_T over a single predicate T) is enumerated like the shape:
  - Rule 4 does not walk the lace frame by frame: like the CAV25 rewind, the trail of p at (σ, i2) jumps to
    `i_upd = last_upd(σ, i2, p)` and continues on the frame linked to σ^{i_upd} by its **prev** link
    (`TaintingEngine.jumps_up`/`jumps_down`), so `taint_ptr` marks only the ends of the jumps.
  - Rule 5 ends a trail with `points_here`, not the paper's `ptr_here`.
  - Every step propagates all it can at once; consistency between labels is not checked (`consistent` is True).
  - TQ2 (a trail walking through another trail's seed) is replaced by the three places where two trails of the same
    pointer can merge under jumps: two entries leaving a label through the same `last_upd` frame, a jump landing on a
    seed, the T1 seed on a field seed (rationale in the `shape.py` docstring). TQ4's ⟨pf := here⟩ is never produced.
  - `free p` sets every pointer variable on the freed node to nil, so a dangling pointer *variable* cannot be
    expressed; dangling-pointer tests must go through a field.

## Repository notes

- `notes/predicates.md` (+ `notes/rsc/*.png`) is the reference list of the paper's predicates/formulas the engine
  implements; consult it alongside the PDF when touching a `step_*` method.
- `enum_models/__init__.py` (`KnittedTrees`, `generate_labels`) is a legacy wrapper whose `LabEngine(...)` call no
  longer matches the constructor; the live entry points are `chc/Lab/system.py::build_lab` and
  `chc/pre/__init__.py::make_system`.
- The repo root contains large generated artifacts (`*.smt2`, `*.log`, `prolog.horn`, `smt/`, `.profile/`); don't read
  them whole and don't commit them.
