.PHONY: check

check:
	uv run --locked ruff check src tests
	uv run --locked mypy
	uv run --locked pytest --ignore=tests/live
