# Contribuir

Use Python 3.12 e `uv sync --locked --group ui`. Execute `make check` ou os comandos equivalentes:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest --cov=app --cov-report=term-missing
```

A suíte usa SQLite localmente. Para executar contra PostgreSQL, configure `TEST_POSTGRES=1` e a URL de um banco descartável com pgvector. A suíte cria esquemas temporários. Execute a avaliação em um corpus limpo e mantenha documentos, respostas e referências em português. Use dados fictícios e deixe segredos fora do Git.
