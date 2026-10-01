# Repository Guidelines

## Project Structure & Module Organization

`main.py` provides the report CLI, `gui.py` starts the local Flask interface, and `models.py` defines shared data classes. Keep parsing, history, catalog, rendering, and web logic in their matching `core/` modules. Report HTML lives in `templates/`; the web interface uses `core/web/templates/` and `core/web/static/`. Tests are in `tests/`, sample Robot output is in `example/`, and `scripts/update_robot_results.py` manages the system results catalog under `robot-results/`.

## Build, Test, and Development Commands

- `python -m pip install -e '.[dev]'`: install the package and pytest for local work (Python 3.9+).
- `python main.py --results-dir example --report /tmp/relatorio.html --no-history`: generate a report from sample results without changing history.
- `python gui.py`: start the local web interface; `robot-report-gui` is the installed equivalent.
- `python main.py --catalog-dir robot-results/systems --report /tmp/catalog.html`: build a consolidated catalog report when catalog data is present.
- `python3 -m unittest discover -s tests -v`: run the standard test suite. `pytest -v` is also supported.

## Coding Style & Naming Conventions

Use four spaces for Python indentation and follow the existing PEP 8 style. Name modules and functions in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Add type hints to new Python interfaces and keep the parser, renderer, and web responsibilities separate. There is no configured formatter or linter; match nearby code and keep imports organized.

## Testing Guidelines

Tests use `unittest` classes and assertions, with files named `test_*.py` and methods named `test_*`. Add tests beside related coverage in `tests/` for behavior changes, especially CLI exit codes, report output, and history handling. Browser tests are opt-in: after installing Playwright and Chromium, run `ROBOT_REPORT_BROWSER_TESTS=1 python -m unittest tests.test_catalog_browser -v`. No coverage percentage is configured.

## Commit & Pull Request Guidelines

Recent commits commonly use short `feat:` or `fix:` subjects; follow that pattern with an imperative summary of the change. In pull requests, describe the user-visible behavior, list the tests run, and link a relevant issue when available. Include screenshots for web interface or report layout changes. Keep generated `output.xml`, `history.json`, and `relatorio*.html` out of commits unless they are intentional fixtures; root output files are ignored by Git.
