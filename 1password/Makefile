.PHONY: test test_lint test_unit

test: test_lint test_unit

test_lint:
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .

test_unit:
	uv run --frozen pytest
