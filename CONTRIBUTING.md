# Contributing

Contributions are welcome through GitHub issues and pull requests.

## Scope

This repository is an integration: it connects the MyQ API to Home Assistant
and exposes entities (covers, sensors, cameras, etc.) and the logic needed
to keep them accurate.

Out of scope:

- custom panels, dashboard cards, or other frontend UI;
- dashboard layouts, automations, or other functionality better implemented
  using existing Home Assistant entities and services.

If you want to build UI on top of MyQ entities, please publish it as a
separate project (e.g. a HACS frontend plugin).

## Before you open a pull request

- For anything beyond a small bug fix, open an issue first and wait for
  agreement on the approach. Pull requests for new features without a
  prior discussion may be closed without review.
- Keep pull requests small and focused on one change.

## AI-assisted contributions

Using AI tools is fine. Submitting code you do not understand is not.

- You must understand every change in your pull request and be able to
  explain why it is written that way.
- Maintainers may ask questions about your code. If you cannot answer
  them yourself, the pull request will be closed.
- Disclose AI assistance in the pull request description.

## Development setup

Use Python 3.14 or newer and install the test dependencies:

```bash
python -m pip install -r requirements_test.txt
```

Before opening a pull request, run:

```bash
ruff check .
ruff format --check .
mypy custom_components/myq tests
pytest
```
