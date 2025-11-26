# TreehornX

**TreehornX** is a tool for verifying heap-manipulating programs.

------------------------------------------------------------------------
## Code of Conduct for Developers

Please follow these guidelines when contributing to the project:

- Be respectful, professional, and collaborative in all communications and contributions.
- Follow repository conventions (commits, PRs, issue templates) and keep changes focused and well-documented.
- Static analysis and CI checks are required safety measures. Do not bypass or disable them casually.
- If you believe a check must be bypassed, only do so when you are 100% sure of the consequences. In that case:
    - Get approval from a maintainer before bypassing.
    - Record the reason and context in the pull request and commit message.
    - Add tests or other mitigations to cover the change.
    - Re-enable the checks as soon as the issue is resolved.
- When in doubt, ask a maintainer or teammate for review.

## 🚀 Installation

### 1. Install **uv**

``` bash
pip install uv
```

### 2. Clone the repository

#### HTTPS

``` bash
git clone https://github.com/mfaella/TreehornX.git
cd TreehornX
```

#### SSH

``` bash
git clone git@github.com:mfaella/TreehornX.git
cd TreehornX
```

### 3. Install dependencies

``` bash
uv sync
```
If you work as developer on this project run
```
uv run task dev-env
```
This command will enable pre-commit checks on your work, if a check step fail the commit is aborted. Remember that such checks will be run in the CI/CD pipeline anyway, so don't waste github processing resources uselessly.

### 4. Format, Validate and Test the project

```bash
uv run task format
uv run task validate
uv run task test
```

Execute these commands all at once with
```bash
uv run task verify
```

#### About testing
Is required an branch and statement coverage of 85%. Check it with
```bash
uv run task coverage
```

------------------------------------------------------------------------

## 📚 Documentation

Generate and view the project documentation:

### Build Documentation

``` bash
uv run task docs
```

### View Documentation

Open `docs/build/html/index.html` in your browser, or serve it locally:

``` bash
uv run task docs-serve
```

Then navigate to http://localhost:8000

### Clean Documentation

``` bash
uv run task docs-clean
```
