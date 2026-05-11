# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.11 Streamlit proof of concept for an NBIM daily news digest. The UI entry point is `app.py`. Core package code lives in `src/nbim_digest/`, with modules for ingestion, rule filtering, LLM calls, storage, pipeline orchestration, and UI formatting. Configuration is kept in `config/*.yaml`; demo fixtures and cached model outputs are in `data/`. Tests live in `tests/` and mirror package behavior by feature, for example `tests/test_rule_filter.py` and `tests/test_storage.py`. Static assets are under `assets/`, currently including the NBIM logo.

## Build, Test, and Development Commands

- `python3 -m venv .venv && source .venv/bin/activate`: create and activate a local environment.
- `pip install -r requirements.txt`: install runtime and test dependencies.
- `pip install -e .`: install the `nbim_digest` package from `src/` in editable mode.
- `streamlit run app.py`: run the local Streamlit app.
- `python3 -m pytest -q`: run the full test suite.

Demo mode can run without API keys when cached outputs are enabled. For live Anthropic analysis, copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

## Coding Style & Naming Conventions

Use standard Python style: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and clear module names matching their responsibility. The codebase uses type hints, dataclasses, and small focused modules; follow those patterns for new logic. No formatter or linter is configured in `pyproject.toml`, so keep changes PEP 8 compatible and consistent with nearby code.

## Testing Guidelines

Pytest is the test framework. Add tests in `tests/` using `test_*.py` files and descriptive test names such as `test_direct_oljefondet_reference_passes_with_signal`. Prefer focused unit tests for taxonomy, filtering, storage, and environment handling. For pipeline or UI changes, include coverage for demo fallback and avoid requiring live API keys unless the test is explicitly marked or isolated.

## Commit & Pull Request Guidelines

The current history uses concise, imperative commit messages, for example `Build NBIM daily digest POC`. Keep future commits short and outcome-focused. Pull requests should include a brief summary, testing performed, linked issue or task context if applicable, and screenshots for visible Streamlit UI changes. Call out config, prompt, or schema changes explicitly so reviewers can evaluate operational impact.

## Security & Configuration Tips

Do not commit `.env`, API keys, generated SQLite databases, or ad hoc scraped content. Keep source definitions in `config/feeds.yaml` and Google News RSS definitions in `config/google_news_rss.yaml`; this project intentionally uses metadata feeds rather than article scraping.
