# disgrace

A chat app — backend and frontend both live in this repo (see `CLAUDE.md`).

## Stack

Python 3.12 / FastAPI / Uvicorn / SQLAlchemy (async) / Postgres, managed with [uv](https://docs.astral.sh/uv/).

## Local development

Prerequisites: [uv](https://docs.astral.sh/uv/) installed, and a Postgres
server running locally that accepts the default `postgres`/`postgres`
user/password over TCP on `localhost` (matches the default `DATABASE_URL`
in `app/config.py` — override it, e.g. via `.env`, if your local Postgres
is set up differently).

```
uv sync                       # installs Python 3.12 + all dependencies
createdb chat_app_dev
uv run alembic upgrade head   # creates the users/rooms/messages tables
uv run uvicorn app.main:app --reload
```

The API is then live at `http://localhost:8000` (try `curl
http://localhost:8000/api/rooms` — a `401` back means it's up and working,
since that endpoint requires a logged-in session). `--reload` restarts the
server automatically on code changes; drop it for anything resembling
production.

Config is read from environment variables (see `app/config.py`), with sane
local defaults — `DATABASE_URL`, `SECRET_KEY`, `SOCKET_ORIGINS`. Create a
`.env` file in the project root to override any of them locally instead of
exporting shell variables.

## Tests

```
createdb chat_app_test
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost/chat_app_test" uv run alembic upgrade head
uv run pytest app/tests
```

## Manual testing

`dev-client/` is a throwaway, unstyled HTML+JS page for exercising the API
by hand — not the real frontend. It currently still speaks the old Phoenix
Channels wire protocol and needs updating for the new WebSocket message
format (`{"event": ..., "payload": ...}`).

## Reference

`reference-application/` is the original Elixir/Phoenix implementation of
this same API, kept around for reference. It is not run or maintained.
