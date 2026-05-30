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

# PyPI publish checklist:
#   1. Bump version in pyproject.toml
#   2. Commit and tag: git tag vX.Y.Z && git push --tags
#   3. Set TWINE_USERNAME / TWINE_PASSWORD (or use a ~/.pypirc token)
#   4. Run: make publish
publish: check
	rm -rf dist/
	uv run python -m build
	uv run twine upload dist/*
