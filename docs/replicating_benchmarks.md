# Replicating the benchmark results

This guide explains how to reproduce the results produced by
[`scripts/benchmarks.py`](../scripts/benchmarks.py).

## 1. Get the code and its dependencies

### Option A — using `uv` (recommended, matches CI/dev workflow)

```bash
pip install uv
git clone https://github.com/mfaella/TreehornX.git
cd TreehornX
uv sync
```

### Option B — using `pip` and `requirements.txt`

```bash
git clone https://github.com/mfaella/TreehornX.git
cd TreehornX
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

`requirements.txt` only pins the third-party packages declared in
`pyproject.toml`; the `-e .` install is what makes the `treehornx` package
itself importable (`scripts/benchmarks.py` imports from `treehornx.*`).

## 2. Check the CHC solver binary

`benchmarks.py` defaults to the `Golem` CHC solver, pointed at:

```
scripts/solvers/linux/x86-64/golem
```

Make sure the binary is executable:

```bash
chmod +x scripts/solvers/linux/x86-64/golem
```

If you are not on Linux x86-64, replace `default_chc_solver()` in
`scripts/benchmarks.py` with a `GolemSolver`/`Z3CHCSolver` pointing at a
binary built for your platform.

## 3. Input files

The benchmark configurations reference C files under `scripts/c_files/`.
The list in `benchamrks_config` (top of `scripts/benchmarks.py`) enumerates
every file/context combination that is run; nothing else needs to be
prepared.

## 4. Run the benchmarks

From the repository root:

```bash
# with uv
uv run python3 scripts/benchmarks.py

# with a plain venv
python3 scripts/benchmarks.py
```

Each configuration is solved with a 1500-second timeout (see the
`timeout=1500` argument to `run_benchmark` in `main()`).

## 5. Read the results

The script writes a timestamped CSV file in the current working directory,
e.g.:

```
benchmarks_2026-07-07_12-00-00.csv
```

Each row corresponds to one `BenchmarkConfig` entry and reports, per
verification key (`err`, `oom`, `lof`, `post_is_tree`):

- whether it was trivially safe (no solver call needed),
- system-creation and solving elapsed time,
- whether it timed out,
- the resulting outcome (`safe` / `unsafe` / `unknown`),

plus overall stats such as `number_of_labels`, `longest_label_len`, and
`number_of_tainted_labels`.

## 6. Customizing the run

To reproduce a subset of results or add new ones, edit the
`benchamrks_config` list in `scripts/benchmarks.py`: each `BenchmarkConfig`
takes the C file to analyze plus optional `n`, `m`, `c` label-generation
parameters, a `pre_ctx`/`post_ctx` (from `treehornx.chc.SDTAContext`), and a
`solver` override.
