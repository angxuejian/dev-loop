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

2. Copy the environment configuration

   ```bash
   cp .env.example .env
   ```

   Then update the following parameters in .env:

   - `GITHUB_BASE_URL`: The base URL of GitHub.

## Frontend commands

```bash
npm run lint
npm run format
npm run typecheck
```

## Backend commands

```bash
uv run ruff check .          # Check Python code
uv run ruff check . --fix    # Apply automatic fixes
uv run ruff format .         # Format Python code
uv run ruff format --check . # Check formatting without changes
uv run pyright               # Check Python types
```
