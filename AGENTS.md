# Project Instructions

## Development

- Read the relevant feature specification before making changes.
- Follow the existing project architecture and coding style.
- Do not modify unrelated files.
- Do not skip lint, formatting, or type checking.

## Frontend validation

Run:

npm run lint
npm run format
npm run typecheck


## Backend validation

Run:

uv run ruff check . --fix
uv run ruff format .       
uv run pyright

## Git

- Use Conventional Commits.
- Do not commit generated, temporary, or unrelated files.
- Only commit after all required checks pass.
- Keep each commit focused on a single logical change.

### Commit Message

Format:

<type>(<scope>): <description>

- `type`: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, etc.
- `scope`: Logical module or affected area (optional).
- `description`: A concise description of the change.

Examples:

feat(auth): add token validation
fix(dashboard): update chart title
refactor(api): simplify time window validation
docs: update quick start guide
chore: update dependencies