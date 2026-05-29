# SmartCore

SmartCore is a personal student secretary system. The v1 goal is to run a server-controlled schedule, assignment, reminder, Feishu bot, internal web panel, and backup workflow with low external API usage.

See the architecture documents in [doc/](./doc/README.md).

## Development

The project uses Python FastAPI, SQLite, SQLAlchemy, APScheduler, and pytest.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Security

Do not commit real secrets, databases, or backups. `passwd.txt`, `.env`, `data/`, and `backups/` are ignored by Git.

