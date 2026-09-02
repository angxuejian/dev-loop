# dev-loop

An AI-powered development loop that plans, implements, tests, reviews, and iteratively fixes code until it's ready for human approval.

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
