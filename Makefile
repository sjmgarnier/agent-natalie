.PHONY: lint format typecheck security test check install-hooks

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
