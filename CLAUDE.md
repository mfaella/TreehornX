# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

TreehornX is a research prototype that verifies memory safety of C programs manipulating trees and lists. It implements
the knitted-tree / CHC method of Faella & Parlato, *Verifying Tree-Manipulating Programs via CHCs* (CAV25, extended
version in `notes/`), and adds **preconditions** expressed as symbolic data-tree automata (SDTAs) and the
**tree-shape check** of the output heap (tainting, Sec. 6 of the POPL27 draft in `.notes/`) and the **postcondition
check** of the output tree (Sec. 7, the S predicate over output states, `--post`).

## Commands

Dependencies are managed with `uv`. The project runs on PyPy 3.11 (`.python-version`), so code must stay 3.11-compatible:
no PEP 695 generics/`type` aliases, `override` comes from `typing_extensions`. There is no SMT library dependency:
quantifier-free terms are the in-house `smt` package, clauses the in-house `analysis/chc/smt` package, and solvers run as
external processes.

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
uv run treehornx verify FILE.c --pre bst --post bst --check-sat         # also check that the output tree is a bst
uv run treehornx verify FILE.c --pre bst --eq-prop 2 --const-prop 2 --check-sat   # with the eq/const phases
uv run python scripts/benchmarks.py [--only SUBSTR] [--timeout S] [--out FILE.csv]
```

- Integration tests call the `z3`/`eld` binaries and are skipped when they are not found. Solver binaries are shipped
  under `scripts/solvers/linux/x86-64/` (z3, golem) and `tests/integration/solvers/` (eld, golem); the CLI takes
  `--solvers-dir` and falls back to `PATH`. `PortfolioSolver` writes the system to a temporary file and races golem,
  z3 and eldarica on it (first sat/unsat wins, the others' process groups are killed); golem has no timeout flag, so
  it is killed when the timeout expires.
- Terms carry their own types and predicates their own signatures, so several systems can be built in one process
  without resetting any environment. Terms are interned in weak pools (identity equality, `src/treehornx/intern.py`);
  `tests/reset_env.py::reset_env()` (test helper, with `snapshot`/`restore`) empties them, after which older terms are no longer equal to new ones.
- Interning: `@intern` (`treehornx/intern.py`) on a frozen dataclass makes the constructor raise and adds the
  keyword-only `X.make(field=...)`, which returns the live instance with the same fields (key = field values in
  parameter order + their types, so `True`/`1` and keyword order do not matter; weak pool; optional static
  `__intern_args__` normalizes the arguments; `reset_pool(cls)`, `pool_of(cls)`). Pyright does not see `make`:
  each class declares its signature under `TYPE_CHECKING`. Interned classes: `Constant`, `Var`, `OpExpr`,
  `Predicate`, `Application`, `Clause`, `Lab`, `TLab`.
- `docs/replicating_benchmarks.md` explains how to reproduce the paper benchmarks (they were produced on the `post`
  branch).
- Tree-shape tests: `tests/integration/test_tree_shape.py` (`*_shape_*` programs, each also checked memory safe;
  safe cases also assert that `finals()` has a root, so SAT is not vacuous), `test_tree_shape_pre.py` (`*_pre_shape_*`
  programs whose verdict depends on the precondition), `test_cli_tree_shape.py`; unit tests in `tests/unit/enum_models/test_taint.py` (including completeness of
  `finals()` against per-tree fixpoints) and `test_shape.py`. `TestConfig.layer = "tree_shape"` selects `TreeShape.make_system`.
- Postcondition tests: `tests/integration/test_post.py` (programs that are memory safe and build a tree, with
  `pre`/`post` pairs), `test_cli_post.py`, `tests/unit/analysis/chc/test_post_symbols.py`. `TestConfig.layer = "post"` with
  `TestConfig.post` selects `Post.make_system`.
- Must-analysis tests: `tests/unit/analysis/abstract_interpretation/must/test_must.py` (`UnionFind`, `MustEqualityEngine`,
  `MustConstantEngine`, `EqConstrTLab` on labels built by hand: `must_helpers.py::FakeLabel`; `conftest.py` installs a
  stub of `commons.ConstrTLab` only when the real one cannot be imported).
- ConstrTLab tests: `tests/unit/analysis/chc/test_constr_tlab.py` (printed predicates take exactly `args`, the
  symbols removed by the phases leave the clauses, the phases compose in both orders).

## Pipeline

`main.py` (Typer CLI, output helpers in `tui.py`) runs:

1. **Parse** — `parser.py` lowers a restricted C subset (one `struct`, one `void f(struct NODE *root)`, top-level
   declarations, at most one dereference per statement, no field access inside expressions/conditions) via
   pycparser into `ir.py`. The IR mirrors Sec. 2 of the paper: pointer vars, data vars, pointer fields and data
   fields are four separately-numbered namespaces; the root is pointer var 0; the only branch is `IfGoto`.
   Uninitialised data vars are inputs (nondeterministic), pointer vars are nil.
2. **Enumerate the shape** — `enum_models/LabEngine.py` (on top of the generic worklist fixpoint in
   `symbolic/SymbolicEngine.py`) computes every *label* (a node's log of frames) and every *pair*
   (parent label, child label, child index j) reachable within bounds m (allocations) and n (frames per label).
   The `symbolic` package holds what is generic: `SymbolicEngine[S, C]` over states S and child indices C,
   `Edge[S, C]` (`Pair = Edge[S, int]`; build edges with `Edge(...)`, pyright cannot infer S through the alias),
   `SymbolicTree[S, C]` (fields `edges`, `roots`, `arity`, `leaves`, the splits; it is both the single constructor argument of the engine and the result of `finals()`). The engine keeps plain sets (no interning):
   the states are interned by `TLab.make` (`@intern`; `TaintingEngine` takes it as its keyword-only
   `TLabFactory`), its `Lab` by `Lab.make` (a prefix is always canonical); `labels.py::get_tlab_id` gives each TLab
   an id the first time it is asked (the runner asks in the order of the pairs, so the predicates `<name><id>` come
   out in a fixed order). **There is one label type,
   `TLab.make(taint_node=, taint_ptr=, lab=)`** (`enum_models/labels.py`, with `Lab` and `ExitCode`): `lab` is a
   `Lab`, an immutable linked list of `Frame`s (equality walks the prefixes, the hash is cached), built only with
   `Lab.make(frame=, prefix=)`. `enum_models/frame.py` holds `Frame`/`MutableFrame`, the directions `Dir`
   (`Up | Internal | Down`) and the events `Event`. `LabEngine` is a `SymbolicEngine[TLab]`
   whose `step_int/step_up/step_down` unwrap `.lab`, run the Lab steps (`step_int_lab`, `step_up_lab`,
   `step_down_lab`, on `Lab`) and wrap the results with `untainted` (⊥ node, no trail). The taints stay empty unless
   the check is tree-shape or post. `enum_models` is a single flat package (no subpackages; its `__init__` re-exports nothing, import the modules directly); the tainting helpers are at the end of `enum_models/helpers.py`. Internal transitions use the private
   `_TransitionDirection` (`_Up | _Internal | _Down[C]`). The engine takes one internal step at a time; the
   subclasses can chain them in their `step_int` (`LabEngine(consume_internal_steps=True)` returns only the labels
   with no internal step left, default False; `TaintingEngine.step_int` already loops to a local fixpoint). `steppable` holds the states and edges on which a step
   was taken; `finals()` is a least fixpoint over the saturated edges (no step taken on the edge or its states),
   computed bottom-up from the leaves in linear time (`SymbolicTree.filter_edges`): a state is final when it is a
   leaf or every child index has a saturated edge to a final child. The engine keeps the sets `roots` and `leaves`,
   started from the input tree; a transition adds its new state to the set of its old state (no `is_root`/`is_leaf`
   hooks). Then a DFS from the final roots keeps
   the saturated edges to final children. Infinite trees (a label paired with itself while the lace walks down a
   list) are dropped: their clauses have no base case, so they cannot change the verdict.
   Initial labels/pairs come from the end of `enum_models/labels.py` (CHC I/II: `start_labels` and `backbone_labels`
   return untainted TLabs, `initial_pairs` edges of TLabs; `start_labels` takes `LabEngine.predict_next_dir` as an
   argument, so `labels.py` does not import `next_dir.py`), step predicates of Appendix C are methods
   `step_*_{int,ext,down}`, auxiliary predicates (`points_here`, `stop_rewind`, `rewind_target`, …) live in
   `enum_models/helpers.py`.
3. **Data constraints** — `analysis/chc/Lab/system.py::build_lab` keeps the final labels and pairs (`LabCHC.tree` is a
   `SymbolicTree[TLab]`) and `LabCHC.builder`, a `ConstraintsBuilder` without automata. `analysis/constr/ConstraintsBuilder.py`
   makes every constraint (Lab, pre, post). The data of a label are the symbols `v<id>_<frame>`, `f<id>_<frame>` of
   its kept frames (`kept_frames`, `data_syms`). Lab constraints: `label_constraints` (every step reaching a frame of
   the label: ψ_internal for internal steps, the field copy from the frame below for external steps, CHC II for the
   root, cached per (label, role)) and `consistency_constraint` (data variables equal on the frames of a parent and
   child linked in the lace). `builder.with_automata(pre=ctx, not_post=...)` adds the automata (`pre: PreSymbols`,
   `post: PostSymbols`) and shares the cache; `pre_constraints`/`pre_consistency` and
   `post_constraints`/`post_consistency` read them.
4. **ConstrTLab and the preprocessing phases** (`analysis/constr/`). A `ConstrTLab` is a TLab with its constraints;
   it is the only interface the systems read from a node: `symbols()`/`args(role)`/`arg_types()` (the predicate
   arguments), `constraints(role)`, the static `ConstrTLab.consistency_constraints(parent, child, j)` (parent with
   the role `Parent()`, child with `Child(j)`) and `rename(expr, role)` (an expression on the TLab's symbols, on the label's arguments; used for the
   post error). `ConstrTLab(tlab, builder)` holds all the constraints of the TLab: `label_constraints` and
   `consistency_constraint` of its Lab label and, when `builder.post` (the negated postcondition) is set, the A¬post
   states and S1–S4 (step 8). Each phase is a function `SymbolicTree[ConstrTLab] -> SymbolicTree[ConstrTLab]`
   that builds, from every label and the result of its analysis, a new label that changes the constraints
   (`phases.py`, `map_tree` rebuilds a tree):
   - `lift(tree, builder)`: the TLabs with their constraints.
   - `pre_phase(tree)` → `PreConstrTLab(label)`: the precondition SDTA of `builder.pre` as data. An input node
     (`label[1].active`) gets `pre_n_X` and, for each input child field j (`active_child[j]`, not the parent field),
     `pre_s<j>_X` (`constr/pre.py::PreSymbols`, `symbols.py::PreNodeState`/`PreSlotState`); constraints ψ (frame-1 fields, through
     `label.rename`; nil for a non-input child) and, at a root, ψ_F (or `accept_empty` for an empty input);
     consistency `pre_s<j> = child's pre_n`. Without `--pre` the phase is not applied (every input accepted).
   - `eq_phase(tree, level)` → `EqConstrTLab(label, classes)`: must analysis of the var = var conjuncts by
     `abstract_interpretation/MustEqualityEngine.py` on `abstract_interpretation/MustEngine.py` (see below). Its fact is
     a `networkx.utils.UnionFind` (`utils/union_find.py`, with `of`, `join`, `meet`, `transform`, `restrict`,
     `partition`, `equal`; the module names the operations by the order on facts, the engine by the order on concrete
     states, so the engine's `meet` is `union_find.join` and the engine's `join` is `union_find.meet`).
     `EqConstrTLab` takes `Iterable[set[Symbol]]` and builds its mapping: every class of two or more arguments leaves
     the arguments and is replaced by a new symbol (`commons.symbol_generator`: `I<k>` for Int, `B<k>` for Bool, names
     already in the arguments are skipped) that takes the place of the first symbol of the class. `level` is accepted
     and ignored.
   - `const_phase(tree, level)` → `ConstConstrTLab(label, consts)`: `MustConstantEngine`, whose fact is `ConstFacts`
     (`consts`: variable → constant, closed under `eqs`, a `UnionFind` of the var = var facts that moves the constants
     across edges). The symbols equal to a constant leave the arguments. Two constants in one class are a clash: the
     meet is `BOTTOM`, the alternative is dropped, and a label without a feasible derivation keeps its state unchanged
     in `outputs()`.
   `MustEngine[F]` (`abstract_interpretation/MustEngine.py`) uses the order of concrete states: `BOTTOM` is `false` (no
   derivation, found yet), `meet` (⊓) is the conjunction of the facts of one derivation (parent, child, edge; it may
   return `BOTTOM`), `join` (⊔) the facts common to the alternatives of a slot, `project` forgets symbols, `with_role`
   renames them to `None`/`Parent()`/`Slot(j)`; `equal` compares two facts (the worklist uses it, override it when F has
   no value equality). Bottom-up pass: a leaf has its own facts, a state meets the facts of its label, of each
   alternative child and of the edge, projects them onto its arguments and joins the alternatives of each slot in
   index order. Top-down pass (`top_down`, default True): a root keeps its bottom-up result; a state joins, over its
   parents, the meet of the parent's top-down result, its own bottom-up result and the edge (so the facts of the
   siblings reach it through the parent). Both passes are least fixpoints from `BOTTOM`; `result(label)` is the top-down
   result, else the bottom-up one, else the facts of the label. `EqConstrTLab` and `ConstConstrTLab` substitute the
   symbols of their `mapping` (by a symbol or a constant) in the constraints of `label` and in `rename`.
   `pipeline.py::preprocess(tree, flags)` applies eq then const (`--eq-prop`, `--const-prop`); the CLI order is
   lift (builder with `pre` for `--pre`, `not_post` for `--post`) → pre → eq → const, then `--split`, then the runner.
5. **Bottom-up run (the whole system)** — `analysis/chc/pre/runner.py::BotUpAutomataRunner` (over `ConstrTLab`)
   attaches a predicate `<name><id>` to every label; **its arguments are exactly `label.args(role)` plus the error
   flag `e`**, and nothing rewrites the clauses afterwards (no clause cleaning). Clauses carry `label.constraints`
   of every node and `ConstrTLab.consistency_constraints` with its children, so there are no Lab predicates and no
   clauses for the steps of the lace. The children are collected one at a time: `<name><id>_<N>` holds the parent's
   args and the error flag accumulated so far (`pre_p_e<N>`); `<name><id>` follows from `<name><id>_<k+m>`. The
   automata are in the labels (step 4), not in the runner. Subclasses: `pre/MemoryRunner.py` (exit codes, with
   `label_exit`), `TreeShape/TreeShapeRunner.py`, `Post/PostRunner.py`. `is_error(label, role)` may read the
   node's args (through `label.rename`); `is_pair_error(parent, child, j)` (false by default) is ORed into the
   parent's accumulated flag in `collect_clause`. Builders: `pre.memory_tree`, `TreeShape.tree_shape_tree`,
   `Post.post_tree` (the ConstrTLab trees) and `make_system` of each package.
   Automata are in `analysis/chc/sdta/SDTAContext.py` + `psi.py` (`bst`, `bst_strict`, `sll_sorted`, `sll_sorted_strict`,
   `avl`, `rb`). The ψ functions hard-code the field names (`next`, `left`, `right`, `data`), so input programs
   must use them.
6. **Solve** — `smt/terms.py` (imported as `from treehornx import smt as sx`) holds the quantifier-free terms
   (`Var`, `Constant`, `OpExpr`, no predicates; operators are built as `sx.OpExpr.make(op=sx.Operator.X, args=(...))`, `sx.Max`
   builds the `ite` chain). `analysis/chc/smt/sexpr.py` builds the CHC layer on them (`Predicate`, `Application`, `Clause`,
   and `CHCSystem`, which prints a `HORN` script declaring only the predicates used). Every class of both layers
   is `@intern` (`X.make(...)`, one weak pool per class); `intern.reset_pool(cls)` empties one pool,
   `tests/reset_env.py::reset_env` all of them (tests only);
   `analysis/chc/smt/preprocess.py` has `substitute`/`simplify`/`conjuncts`/`fresh_var`. `analysis/chc/solvers` pipes the
   script into `z3 -in` (`Z3Solver`) or `eld -in` (`EldaricaSolver`) and returns `Status` SAT/UNSAT/UNKNOWN.
   **sat = safe, unsat = an error is reachable.** One system is built per exit status (ERR, OOM, LABEL_OVERFLOW)
   that the enumeration actually reaches; unreached ones are reported as "trivially" safe without calling a solver.
7. **Tree shape (`--tree-shape`, check `TREE_SHAPE`)** — assumes memory safety (the paper's composition
   assumption): with `--tree-shape` or `--post` the CLI does not build the memory systems of step 6, and
   `TaintingEngine.lab_finals` drops the final Lab labels ending in ERR, OOM or label overflow (and their pairs)
   before tainting, so these runs are not in the tree-shape and post systems. Steps:
   - `enum_models/TaintingEngine.py` (a `SymbolicEngine[TLab]`) starts from the final (untainted) TLabs of
     `LabEngine` and saturates Rules 1–5 of POPL27 Fig. 5: `step_int` = T5 (a trail
     ending on the node, via `points_here`, taints it) + T3 (a tainted node seeds a ⊤ trail at the last
     ⟨pf := p⟩ of each field), `step_down` = T2 (structural child) + T4 down, `step_up` = T4 up; T1 seeds
     `taint_ptr[(ROOT, last frame)] = ⊤+` on the end-of-lace label at initialisation. Taints are `BoolPlus`
     (⊥ < ⊤ < ⊤+, merged by join; hashed by value so the systems come out in a fixed order); `TaintPtr` stores only
     non-⊥ keys `(p, frame)`. A step returns None when nothing changes.
   - `finals()` is the generic one (step 2): the labels and pairs on which no step changes the taints, composing
     a tree from the `is_initial` roots. Each child slot is satisfied independently; this is exact because a step
     through slot j excludes the other edges of slot j from the propagation of the new parent
     (`SymbolicEngine._excluded_child`) and steps only join taints.
   - `enum_models/shape.py` reads the violations off the taints (`ShapeError`, POPL27 Fig. 9): `label_errors` (two trails
     ending on a node, a trail ending on a freed node, trails merging, a self-loop) and `pair_errors` (a trail
     landing on a seed, a structural child that is also a trail end or was freed).
   - `analysis/chc/TreeShape/`: `tree_shape_from_lab`/`build_tree_shape` (taints on top of `build_lab`),
     `tree_shape_tree` (ConstrTLab tree, with `pre_phase`), `TreeShapeRunner` (predicates `TreeShape<id>`,
     `is_error` = shape errors of `label.tlab`, `is_pair_error` = shape errors of the pair), `make_system`.
8. **Postcondition (`--post NAME`, check `POST`)** — runs after the tree-shape check and assumes it holds (no shape
   errors in this system). `NAME` is the positive property; `main.POST` maps it to the negated automaton A¬post
   (`not_*_ctx`; rb has none, `rb_struct` checks the red-black structure without the bst order).
   `ConstrTLab` with `builder.post` carries the states of A¬post as data (`analysis/constr/post.py::PostSymbols`): `post_n`
   for an output node (tainted and active),
   `post_s<j>` for each structural child (`enum_models/helpers.py::child_is_struct`), `post_t<p>_<i>` for each key of
   `taint_ptr`. Constraints: S1 (a trail ending on the node carries its state) and S4 (ψ of A¬post on the final
   data fields and the child states: slot, trail of the final ⟨pf := p⟩, or nil) in `ConstraintsBuilder.post_constraints`; S2
   (the two keys of each trail jump, `TaintingEngine.py::links_up`/`links_down`) and S3 (slot = child's node state)
   in `post_consistency`. `Post/PostRunner.py::PostRunner`: the error is ψ_F at the output root (the ⊤+ trail of p̂ ends
   on it, SQ1, through `label.rename`) or `accept_empty_post` (false) on an empty output (SQ2). States flowing
   between subtrees pass through the args of the common ancestor, kept in all its chain predicates.

`feature_flags.py::FeatureFlags` changes the size/shape of the systems, not their meaning: `split` (`--split L`,
`SymbolicTree.split` before building each system: 1 one system per maximal body, 2 per body, 3 per root; solved one
by one, sat iff all sat, `--smt2` writes `<function>_<check>_split<L>/` with an `index.csv`), `prune_pairs`
(`--prune-pairs`, yices2 on the Lab pairs, `Lab/prune.py`), `eq_prop` (`--eq-prop L`) and `const_prop`
(`--const-prop L`), the phases of step 4. There is no clause cleaning (`--clean-clause` was removed).

Conventions: positions inside a label are **1-based** like the paper (`sigma[1]` is the first frame,
`sigma[len(sigma)]` the top one); `σ`/`τ` naming follows the paper (σ sends the lace, τ receives the new frame). Child
indices `j` are 0-based, auxiliary (allocation) children are `j ∈ [k, k+m)`. In clauses the place of a node is its
`Role = Parent | Child(j)` (`analysis/chc/symbols.py`): every function that builds constraints or variables takes an
optional `role`, and `prefix_of(role)` names the symbols `p_…` (parent), `c<j>_…` (j-th child) or bare (None).

## How the implementation differs from CAV25

The paper defines a *single* predicate `Lab(σ)` over the full data signature and lets the CHC solver discover
everything. The implementation follows the paper's "Efficient Implementation" future-work idea instead:

- **Shape is enumerated, data is solved.** All finite-domain frame fields (`active`, `pc`, `upd`, `isnil`, `event`,
  `active_child`, `prev`, `next`) are computed explicitly in Python; only data variables and data fields go to the
  solver. Each enumerated label gets its own predicate (case splitting), so `Ψ_Internal/Ψ_Up/Ψ_Down` reduce to
  equalities over data symbols.
- **Labels have no `avail` / fixed length n+1.** A label is an immutable linked list of frames (`enum_models/labels.py`,
  prefix + top frame), so `len(σ, i)` and the `σ^{<i}` shorthand become `label.prefix` / `label.cut(i)`.
- **`prev`/`next` store only a direction** (`Up | Internal | Down(j)`, `enum_models/frame.py`), not `Dir × index`. The linked
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
  dropped from the predicate's arguments (`ConstraintsBuilder.kept_frames`) and only occur as quantified variables.
- **Only labels on which no step is possible are kept** (`SymbolicEngine.finals`), and the query CHC VI is
  issued on the root of the automaton run (with the trivial automaton when there is no precondition).
- **Event set extended** (`enum_models/frame.py`, rationale in `FORMULAS_UPDATES.md`, in Italian): `FieldHere(pfield)`
  (⟨pfield := here⟩) disambiguates `p->pfield := q` when q already points to the current node; `LOF` marks label
  overflow; `Rewind(i)`/`RwdSpec(i, p)` are the paper's `rwd_i`/`rwd_{i,p}`. `step_assgn_to_field`,
  `is_pfield_*` and `step_assgn_from_field` follow the corrected formulas there (including setting `isnil_p = false`
  when `p := q->pfield` moves down to an implicit child, where the paper would copy the default).
- **Data model.** The paper assumes a single data field `val : D`; the IR supports any number of `int`/`bool` data
  fields and variables. `bool` heap conditions (`b = (p == q)`) and `p->pf == NULL` tests are first-class
  statements rather than being reduced to `p = q` via auxiliary variables.
- **No MemSafety loop.** The CLI checks one `(m, n)` (defaults m=0, n=128 — far above the paper's typical n ≤ 10)
  and reports each exit status separately; it does not increment m/n. Flags `-c`, `--partial-correctness`,
  `--interactive-check-sat` and the dependency-graph options are accepted but ignored.
- **Preconditions** (beyond CAV25, sketched in its Sec. 7): the SDTA reads only the first frame of each input node
  (`is_input_node` = `label[1].active`); non-input/auxiliary nodes get the nil state; the query fires when the root's
  state is accepting (`psiF`, a constraint of the root in `PreConstrTLab`) and the propagated error flag is true.
  An empty input tree is accepted by default (`accept_empty`).
- **Parent field** (`--parent FIELD`, `ir.NodeStruct.parent_field`): the field is nil in every input node
  (`enum_models/labels.py::input_shapes`) and is left out of the children given to ψ, in the precondition runner
  (`PreConstrTLab.input_slots`) and in the postcondition (`analysis/constr/post.py::_post_psi`). The tainting skips it too
  (`TaintingEngine.child_fields`): it seeds no trail (T3) and has no structural child (T2), so writes to it are
  never tree-shape errors and A¬post never reads it.
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

- `src/treehornx/analysis/` is the parent package of the analyses: `chc` (the CHC encoding described above), `commons`
  (`ConstrTLab`, `symbol_generator`), `constraints`, `engines` (the generic symbolic engine and tree) and
  `abstract_interpretation` (`MustEngine` and the equality and constant must analyses). The quantifier-free
  terms (`smt`) stay at the top level, next to `analysis`.
- `notes/predicates.md` (+ `notes/rsc/*.png`) is the reference list of the paper's predicates/formulas the engine
  implements; consult it alongside the PDF when touching a `step_*` method.
- The entry points are `analysis/chc/Lab/system.py::build_lab` and the `make_system` of `analysis/chc/pre`,
  `TreeShape` and `Post` (the old `KnittedTrees` wrapper of `enum_models/__init__.py` was removed).
- The repo root contains large generated artifacts (`*.smt2`, `*.log`, `prolog.horn`, `smt/`, `.profile/`); don't read
  them whole and don't commit them.
