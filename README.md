# dev-loop

An AI-powered development loop that plans, implements, tests, reviews, and iteratively fixes code until it's ready for human approval.

## Project structure

- `backend/`: Python backend package.
- `frontend/`: Frontend source files.
- `scripts/`: Development automation and code review scripts.
- `features/`: Feature specifications.

## quick start

1. Install Nodejs and Python dependencies:

   ```bash
   npm install
   ```

   ```bash
   uv sync
   ```

   This project uses both **npm** and **uv** to manage dependencies.

2. Install and authenticate GitHub CLI.

   Download GitHub CLI from the [official installation page](https://cli.github.com/),
   then authenticate it:

   ```bash
   gh auth login
   ```

   Run `code-fix` script from a workspace checked out to the target pull request branch.

3. Configure the AI code review workflow.

   Add the `GLM_LLM_API_KEY` secret in the repository settings. The workflow
   reads it as `secrets.GLM_LLM_API_KEY` in `.github/workflows/code-review.yml`.
   Configure the review provider and scope in `scripts/common/config.py`:

   ```python
   BASE_URL = "https://api.siliconflow.cn/v1"
   MODEL = "moonshotai/Kimi-K2.7-Code"
   REVIEW_FILE_EXTENSIONS = {".py", ".js", ".ts"}
   REVIEW_DIRECTORIES = {"backend", "frontend"}
   MAX_COMMENT_BODY_BYTES = 10_000
   ```

   Tips: You can replace this model with a local model, but you need to modify
   the configuration yourself.

4. Execute the `create` skill to turn requirements into a feature specification.

   ```bash
   $create Build an asynchronous task queue with concurrency limits and retry support for failures.
   ```

5. Execute the `implement` skill to implement the feature specification.

   ```bash
   $implement features/001-async-task.md
   ```

## Skills and scripts

### Skills

- `create`: Create a numbered feature specification in `features/`.
- `implement`: Implement a feature specification, validate it, and create a pull request.
- `git-commit`: Validate changes and create a Conventional Commit.
- `code-review`: Review pull request changes and post valid review comments.
- `code-fix`: Fix unresolved pull request review comments.

### Scripts

- `scripts/code-review.py`: Run AI code review for a pull request.
- `scripts/code-fix.py`: Wait for review feedback and fix unresolved comments.
- `scripts/build-pages.mjs`: Build all standalone frontend applications for GitHub Pages.
- `scripts/common/config.py`: Configure the code review provider and review scope.
- `scripts/common/github-api.py`: Shared GitHub API helpers.
- `scripts/requirements/code-review.txt`: Dependencies for the code review workflow.

> This project uses `Codex CLI` with models provided by `SiliconFlow`.
