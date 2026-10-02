# Petri Net Web

A web application for working with Petri nets: description intake in three formats
(raw text notation, JSON, interactive form), reachability graph construction
(Karp-Miller coverability tree for unbounded nets), property analysis, interactive
step execution, and exports.

**UI language:** Russian. **Documentation:** English.

## Quick start

```bash
docker compose up --build
# open http://localhost:8080
```

## Configuration

All settings have defaults (see `.env.example`). Create a `.env` file to override:

| Variable             | Default             | Meaning                                        |
| -------------------- | ------------------- | ---------------------------------------------- |
| `APP_PORT`           | `8080`              | Host port for the app                          |
| `LOG_LEVEL`          | `INFO`              | Structured JSON log level                      |
| `DB_PATH`            | `/data/sessions.db` | SQLite sessions file (`petri-data` volume)     |
| `REACH_MAX_MARKINGS` | `50000`             | Safety cap for reachability construction       |

## Layout

```
backend/     FastAPI app (src layout: src/petrinet), Dockerfile, pyproject.toml
frontend/    vanilla JS + Cytoscape.js (CDN), served by the API container
e2e/         Playwright end-to-end tests (own container, Phase 5)
docs/        requirements, architecture, ADRs, test plan/report, decisions log
.opencode/   sub-agent definitions (orchestration workflow)
```

## Checks (all inside containers, run from this directory)

```bash
sudo docker compose run --rm app pytest
sudo docker compose run --rm app ruff check src tests
sudo docker compose run --rm app mypy
```

## Documentation

- [Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Decisions log](docs/DECISIONS_LOG.md)
- [Assumptions](docs/ASSUMPTIONS.md)
