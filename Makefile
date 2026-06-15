# Keep the venv outside ProtonDrive so sync evictions don't corrupt it.
export UV_PROJECT_ENVIRONMENT := $(HOME)/.local/share/agent-natalie/.venv

.PHONY: lint format typecheck security test check install-hooks publish

lint:
	uv run ruff check natalie/ tests/

format:
	uv run ruff format --check natalie/ tests/

typecheck:
	uv run mypy natalie/

security:
	uv run bandit -r natalie/ -ll

test:
	uv run python -m pytest tests/ -v

check: lint format typecheck security test

install-hooks:
	cp scripts/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed."

publish: check
	@git diff --exit-code || (echo "ERROR: working tree is dirty — commit or stash changes before publishing"; exit 1)
	@git diff --cached --exit-code || (echo "ERROR: staged changes present — commit before publishing"; exit 1)
	rm -rf dist/
	uv build
	uv publish --token "$$(grep password ~/.pypirc | cut -d' ' -f3)"
