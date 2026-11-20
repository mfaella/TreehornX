# Report: proposals from the z3 tuning and the DBM analysis

Date: 2026-11-20. This report summarizes the proposals of `BEST_Z3_CONFIG.md` and `DBM_ANALYSIS_REPORT.md` (with
its continuation `DBM_SLOT_ALT_REPORT.md`). For each proposal it gives the evidence, the status in the repository
after commit `6fbc785` ("build the CHC systems from the ConstrTLab tree"), and the next action.

## 1. Summary

| # | Proposal | Source | Evidence | Status in the repository |
|---|---|---|---|---|
| Z1 | Use z3 5.3.3 with five Spacer options | z3 config | rb post rb: 35:36 → 17:22, memory 11.3 → 9.7 GB | binary in the repo root (untracked); the CLI cannot pass the options |
| Z2 | Do not use z3 5.3.1 | z3 config | crash after the proof (`Failed to verify: found`) | 5.3.1 is still the z3 of `tests/integration/solvers` |
| Z3 | Solve pre-split system files, not query cones | z3 config | rb pre/post bst: 808 s → 187 s | done: `--split 1/2/3` |
| Z4 | Add a CLI option for the z3 parameters | this report | the runs of this report needed a shell script | not done |
| D1 | Port the set-valued DBM analysis as a phase | DBM | avl bal 29/30 → **30/30 sat**, group005 104 s | not done; the prototype code is lost |
| D2 | Remove the labels without a feasible derivation | DBM, this session | prototype: 1,511 → 749 labels on avl bal | not done: the const phase finds 408 and keeps them |
| D3 | Keep the precondition states as label data (`PRE_DATA`) | DBM | needed by D1 | done: `ConstraintsBuilder.pre_symbols` |
| D4 | Encode `max` as a disjunction (`MAX_DISJ`) | DBM | needed by the DNF of D1 | not done: `smt.Max` builds an `ite` chain |
| D5 | Disjunctive DBM (a small set of DBMs per label) | DBM slot-alt | avl_h: 4 roots still out of memory with every DBM variant | not done; design only |
| D6 | Faster yices edge pruning | DBM | first version > 15 min on avl_h | not done; `--prune-pairs` is disabled |

Proposals marked "this report" or "this session" come from the runs of 2026-11-20, not from the two source reports.

## 2. Current results (reference for the proposals)

Commit `6fbc785`, z3 5.3.3 with the options of Z1, one file at a time.

| Check | Phases | Systems | Result | Solve time | Peak |
|---|---|---|---|---|---|
| `rb_safe_insert` pre rb / post rb, `--parent parent --split 1` | eq 2 | 36 | 36/36 sat | 125 s | 5.3 GB |
| `avl_safe_insert_bal` pre avl / post avl, `--split 1` | eq 2 + const 2 | 42 | 41/42 sat | 55.5 s (sat files) | 0.46 GB |
| same, group005 (roots 21–36, 3,847 predicates) | eq 2 + const 2 | 1 | out of memory | 134 s | 8.4 GB |

So rb is verified. AVL insertion is not: group005 needs a relation between the heights that only the DBM analysis
(D1) gave.

## 3. Proposals from `BEST_Z3_CONFIG.md`

### Z1. z3 5.3.3 with five Spacer options

```
fp.spacer.global=true
fp.spacer.max_num_contexts=50
fp.spacer.native_mbp=false
fp.spacer.gg.concretize=false
fp.spacer.eq_prop=false
```

- `global=true` (global guidance) is necessary: without it, the large rb post cones do not end.
- `max_num_contexts=50` (default 500) decreases the memory: one SMT context per predicate is the main cause of the
  memory growth.
- `gg.concretize=false` and `eq_prop=false` were measured only together.

Evidence (query splitter, 133 cones, rb insertion):

| Pre / post | Old options on 5.3.1 | This configuration on 5.3.3 |
|---|---|---|
| rb / rb | 35:36, 11.3 GB | **17:22**, 9.7 GB |
| rb / bst | 6:03, 4.2 GB | 5:57, 4.1 GB |
| bst / bst | 13:13, 2.6 GB | 13:28, 2.75 GB |
| rb_struct / rb_struct | crash on cone 98 | **12:48**, 9.2 GB |
| rb / rb_struct | out of memory on cone 101 | **13:11**, 8.8 GB |

The gain is large when the post is `rb` or `rb_struct`, and zero when it is `bst`.

Next action: measure `gg.concretize=false` and `eq_prop=false` one at a time.

### Z2. Do not use z3 5.3.1

z3 5.3.1 can crash in `pred_transformer::frames::simplify_formulas` after Spacer has proved the system, so the
result is lost. The crash depends on the order of the `forall` binders, which depends on the variable names.

Next action: replace `tests/integration/solvers/z3` (5.3.1) with 5.3.3, or make the tests use the binary in the
repository root.

### Z3. Pre-split system files

Same check (rb insert, pre bst / post bst), same z3 configuration:

| Method | Files | Time | Peak |
|---|---|---|---|
| Query splitter (cones) | 133 | 808 s | 2.75 GB |
| Split per body | 70 | 333 s | 3.0 GB |
| Split with collapsed bodies (now `--split 1`) | 37 | **187 s** | 3.0 GB |

Status: done. `SymbolicTree.split` gives the three levels; `--split 1` is the collapsed split.

### Z4. A CLI option for the z3 parameters (new)

`Z3Solver` already takes `options`, but `make_solver` in `main.py` does not pass any. The runs of this report wrote
the systems with `--smt2` and called z3 from a shell script.

Next action: add `--z3-option KEY=VALUE` (repeatable), or `--z3-best` for the configuration of Z1.

## 4. Proposals from `DBM_ANALYSIS_REPORT.md` and `DBM_SLOT_ALT_REPORT.md`

### D1. The set-valued DBM analysis

**What it computes.** For each label, facts `x - y ∈ S` between the symbols of the label, where `S` is a set of at
most 5 integers. The facts go into the clauses as the bounds `min(S) <= x - y <= max(S)`.

**How.** On the generic `MustEngine`, bottom-up and then top-down (`io` mode):

1. Write the constraints of the label as a DNF of cubes (lift `ite`, expand Bool `=`/`=>`; drop the literals that
   are not kept, which is a weakening).
2. In each cube, close the linear equalities with a union-find with offsets, then the sets with Floyd–Warshall on
   sets.
3. Use the inequalities on the `height` symbols only as **filters**: an interval Floyd–Warshall removes values and
   cubes.
4. Join over the cubes and the edges; drop a set with more than 5 values (widening).

**Key ingredient: the inequality filter.** A node with two children has 4 `max` cubes (pre and post each take the
left or the right child). In the two "crossed" cubes the conditions of the two `max` contradict each other, but only
the inequalities show it. Without the filter, the crossed cubes survive and the join loses `post_n_height -
pre_n_height` on about 600 of 749 labels; with it, 432 labels get a known set.

**Evidence (avl bal, split 1, z3 with `order_children=1`):**

| File | Without the analysis | With the analysis |
|---|---|---|
| group005 | out of memory (11 GB, 199 s) | **sat, 104 s, 6.8 GB** |
| group024–028 | 8.7–21.9 s | 2.2–2.8 s |
| All files | 29/30 sat | **30/30 sat, 123 s** |

Analysis time: 11 s (the earlier zone analysis with yices needed 50 min).

**Limit.** On `avl_safe_insert_h` (height field) the analysis gives no gain: the must analysis already puts the
output and the input height of a node in one class, and the bounds fall on program variables.

**Status.** Not in the repository. The prototype was in a session scratchpad that no longer exists, so the code
(`dbm.py`) must be written again. The repository now has the parts it needs: `MustEngine`, the phase interface
(`ConstrTLab` wrappers), the pre states as label data (D3).

**Next action.** Write `MustDBMEngine` as a third phase after eq and const, in `io` mode with the `height` filter,
and add its bounds through a `ConstrTLab` wrapper. First target: avl bal group005 (out of memory now).

### D2. Remove the labels without a feasible derivation

A label whose every case is infeasible can be removed with its edges, without a change of meaning.

| | Infeasible labels found on avl bal | Removed |
|---|---|---|
| Prototype must analysis (`REL_PRUNE=1`) | 762 (1,511 → 749) | yes |
| Current const phase | 408 (all from the label's own constraints) | **no** |

In this session, removing the 408 labels makes the tree 1,511 → 1,083 labels but keeps 109 roots and 42 systems:
smaller systems, not fewer. The prototype found more because of the DNF and the inequality filter (D1).

Next action: in `MustEngine.outputs`, drop the labels with a `BOTTOM` bottom-up result and call
`SymbolicTree.filter_edges`; then count again with the DBM phase.

### D3. Precondition states as label data (`PRE_DATA`)

The DBM relates the input and the output height of the same node, so both states must be data of the label.
Status: done. `ConstraintsBuilder.pre_symbols` makes `pre_n_<STATE>` and `pre_s<j>_<STATE>` arguments of the label.

### D4. `max` as a disjunction (`MAX_DISJ`)

`h = max(h1, h2) + 1` is written as `(h1 < h2 ∧ h = h2 + 1) ∨ (h1 >= h2 ∧ h = h1 + 1)`. The DNF of D1 then gets one
cube per case, with the inequality that the filter uses. Status: not done. `smt.Max` builds an `ite` chain; the DNF of
D1 can lift the `ite` instead, so this proposal may become part of D1.

### D5. Disjunctive DBM (for avl_h)

**Problem.** On avl_h with split 3, 67 of 71 systems are sat; roots 30, 32, 38, 40 run out of memory. A Spacer trace
shows that z3 proves the property one height value at a time (`hl > 1`, `hl > 2`, ...).

**Cause.** "A subtree grows only if its root was balanced" is a disjunction inside one label:

```
(post_n - pre_n = 0) ∨ (post_n - pre_n = 1 ∧ pre_s1 - pre_s0 = 0)
```

A DBM is a conjunction of independent sets, so every DBM that contains both cases also contains the excluded pair.
The variant that keeps the slot alternatives apart (`DBM_SLOT_ALT=1`) fixes the root bound of roots 38 and 40, but
z3 still fails on all 4: the same 48 labels keep the value ±2, because the loss happens inside the child label.

**Proposal.** Keep up to `K` DBMs per label (for example `K = 4`); join two of them only above `K`, the two that differ
least. With three slots and four cubes, at most 256 `solve` calls per edge.

**Alternative.** Split each label on the value of its growth `post_n - pre_n` only. Splitting on all pairs gave more
than 200,000 states on avl bal.

Status: design only. Depends on D1.

### D6. Faster yices edge pruning

The exact check of each edge with yices (QF_LIA) was still running after 15 min on avl_h (16,139 edges): it
translated the constraints again and made a new context for each edge.

Proposal: translate each label once; one context per parent, with push/pop for each child.

Status: not done. `--prune-pairs` prints a warning and is ignored in the current pipeline.

## 5. Suggested order

1. **Z4, Z2**: small changes; they make every later measurement simpler and safer.
2. **D2**: small change in `MustEngine.outputs`; gives smaller systems now.
3. **D1** (with D4 inside its DNF): the only measured way to verify AVL insertion (group005).
4. **D5**: only after D1, and only if avl_h is a target.
5. **D6**: optional; D1 and D2 remove part of the same infeasible edges.

## 6. Sources

- `BEST_Z3_CONFIG.md` (2026-11-09/10): z3 configuration and split results.
- `DBM_ANALYSIS_REPORT.md` (2026-11-16): the DBM analysis and its results on avl bal, avl_h and rb.
- `DBM_SLOT_ALT_REPORT.md` (2026-11-16): why z3 fails on avl_h, the slot-alternative variant, the disjunctive DBM.
- Runs of 2026-11-20 (this session): rb and avl results of Section 2, the infeasible-label counts of D2.
