# Contributing

Contributions are welcome: bug reports, new notification targets, fixes and
docs.

## Reporting issues

Open an issue with your Sonarr version, how you run the app (Docker or local),
your configuration with secrets removed, and the relevant log output.

## Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --dev
cp .env.example .env   # fill in your webhook and Sonarr settings
```

Before opening a PR, run the same checks as CI:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy src/new_seasons_reminder
uv run pytest
```

## Pull requests

- Fork, branch from `main`, and keep each PR focused on one change.
- Add tests under `tests/` for new behaviour.
- Update the README and `.env.example` when you add or change a setting.
- Use [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `chore:`). Releases are generated from commit
  messages by python-semantic-release, so the type decides the version bump.
- Don't edit `CHANGELOG.md` or the version by hand.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
