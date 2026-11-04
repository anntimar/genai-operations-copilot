setup:
	uv sync --locked --group ui

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy app
	uv run pytest --cov=app --cov-report=term-missing

up:
	docker compose up --build -d --wait

seed:
	uv run python -m scripts.seed

evaluate:
	uv run python -m app.evaluation.run
