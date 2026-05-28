lint:
	uv run --frozen ruff format && \
	uv run --frozen ruff check --fix

typecheck:
	uv run --frozen mypy .

test:
	uv run --frozen pytest -s -vv --cov=src --cov-report=term-missing tests
