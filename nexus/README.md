# Nexus

A personal productivity and AI workspace for the desktop — notes, tasks, files,
an AI assistant, automation, and a dashboard — in one local-first, fully typed,
tested Python application.

Everything runs on your machine. Data lives in a local SQLite database with
sensitive fields encrypted at rest, and the AI assistant works out of the box
with a zero-cost offline provider until you choose to plug in a real model.

---

## Highlights

- **Notes** — markdown notes with tags, `[[wiki links]]`, backlinks, full
  version history, and full-text search.
- **Tasks** — projects, a drag-and-drop kanban board, due dates, recurring
  tasks, and a calendar view.
- **Files** — index folders, full-text search over their contents (SQLite
  FTS5), content-preview, and a duplicate finder.
- **AI assistant** — persistent chat sessions plus one-shot document tools
  (summarise, explain code, rewrite, draft an email) and local semantic search
  over your indexed files.
- **Automation** — a rule engine ("when *this event*, if *these conditions*, do
  *these actions*"), a scheduler, and folder watching.
- **Dashboard** — headline stats, storage usage, a productivity chart, a
  recent-activity feed, and unified search across every module.
- **Three front ends over one core** — a PySide6 desktop app, a scriptable CLI,
  and an optional local REST API — all sharing the same tested services.
- **Extensible** — a small plugin system and portable ZIP export/import.

## Requirements

- Python **3.13+**
- A desktop environment for the GUI (the CLI and API are headless).

## Installation

```bash
# from the nexus/ directory
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The AI assistant talks to language models through **AIForge**, the
provider-abstraction framework in this repository's root. It isn't on PyPI, so
install it from there to enable real providers (the assistant still runs
without it using the built-in offline provider, and tells you clearly if a
real provider is requested while it's missing):

```bash
pip install -e ..                    # installs AIForge from the repo root
```

## Running

### Desktop app

```bash
nexus                 # launches the GUI
python -m nexus       # same thing
```

### Command line

The CLI gives headless access to the same workspace (stdout stays clean for
scripting; logs go to stderr and a log file):

```bash
nexus notes add "Buy milk" --tags home,food
nexus notes list
nexus tasks projects
nexus tasks add 1 "Prepare slides"
nexus tasks board 1
nexus export ~/backups/workspace.zip
nexus import ~/backups/workspace.zip
nexus plugins
nexus --help
```

### Local REST API

Off by default; when started it binds to localhost and requires a bearer token
(printed at startup, or set `NEXUS_API_TOKEN` to fix it):

```bash
nexus serve --port 8770
# in another shell:
curl -H "Authorization: Bearer $NEXUS_API_TOKEN" http://127.0.0.1:8770/api/notes
```

Routes: `/health`, `/api/notes`, `/api/notes/{id}`, `/api/projects`,
`/api/projects/{id}/board`, `/api/tasks`, `/api/dashboard/stats`, `/api/search`.

### Try it with sample data

```bash
python -m nexus.demo --data-dir /tmp/nexus-demo
nexus --data-dir /tmp/nexus-demo         # opens a workspace pre-filled with content
```

## Configuration

Configuration is optional — the built-in defaults are a complete, valid setup.
To customise, copy [`config.example.yaml`](config.example.yaml) to your data
directory as `config.yaml` (it's picked up automatically) or pass it with
`nexus --config path/to/config.yaml`.

Precedence, lowest to highest: **built-in defaults < `config.yaml` <
environment variables** of the form `NEXUS_<SECTION>_<KEY>`
(e.g. `NEXUS_UI_THEME=light`).

### Using a real AI provider

The default provider is `fake`: no API key, no network, no cost. To use a real
model, install AIForge (above), then set the provider and export your key:

```yaml
# config.yaml
ai:
  default_provider: anthropic
```

```bash
export ANTHROPIC_API_KEY=sk-...       # keys are read from the environment, never stored
```

## Where your data lives

Under one platform data directory (override with `--data-dir`):

| Platform | Location |
| --- | --- |
| Linux | `~/.local/share/nexus` (or `$XDG_DATA_HOME/nexus`) |
| macOS | `~/Library/Application Support/nexus` |
| Windows | `%APPDATA%\nexus` |

It contains `nexus.db` (the database), `backups/` (rotating snapshots taken on
startup and on demand), `logs/`, and `nexus.key` (the encryption key, created
with owner-only permissions). Sensitive columns are encrypted with this key, so
keep it safe — and note that it stays local, which is why an export is portable
plaintext JSON by design.

## Architecture

A strict layering keeps business logic UI-free and independently testable:

```
  UI (PySide6)     CLI        REST API        <- three front ends
        \           |           /
             AppContext                        <- composition root: builds everything
                 |
   Services: notes tasks files ai automation dashboard
                 |         (return frozen DTOs, publish events, raise typed errors)
        Database (SQLAlchemy 2.0 + SQLite)      Event bus
        migrations · encryption · backups · FTS5
```

- **Services** own all logic. They accept dependencies by constructor
  injection, return frozen dataclass **DTOs** (never live ORM objects), publish
  domain **events** on an in-process bus, and raise a typed error hierarchy.
- **Panels / CLI commands / API routes** are thin: they call a service and
  render its DTOs. None of them touch the database.
- **AppContext** is the single place that wires the database and every service
  together, so standing up the whole backend — in memory, for a test — is one
  call.

More detail lives in the module docstrings; every file explains *why* it is
shaped the way it is.

### Project layout

```
nexus/
├── config.example.yaml        # annotated sample configuration
├── pyproject.toml
├── src/nexus/
│   ├── core/                  # config, logging, events, errors, paths
│   ├── db/                    # models, migrations, encryption, backups, engine
│   ├── services/              # notes, tasks, files, ai, automation, dashboard, transfer
│   ├── ai/                    # embeddings + local vector store
│   ├── automation/            # scheduler, rule engine, folder watcher, actions
│   ├── ui/                    # PySide6 window, panels, dialogs, theme, shortcuts
│   ├── api/                   # aiohttp REST server
│   ├── plugins/               # plugin discovery + lifecycle
│   ├── app_context.py         # composition root
│   ├── cli.py                 # `nexus` command
│   └── demo.py                # sample-data seeder
└── tests/                     # unit, integration, and offscreen widget tests
```

## Plugins

A plugin is any object with a `name` and an `activate(context)` method,
discovered from the `nexus.plugins` entry-point group. On activation it
receives the live `AppContext`, so it can subscribe to events, register new
automation actions on `context.automation_actions`, or call any service:

```python
class GreeterPlugin:
    name = "greeter"

    def activate(self, context):
        def greet(event, params):
            print("greetings from a plugin!")
        context.automation_actions.register("greet", greet)
```

Expose it in your package's entry points:

```toml
[project.entry-points."nexus.plugins"]
greeter = "my_package:GreeterPlugin"
```

## Development

```bash
ruff check src/ tests/          # lint
ruff format src/ tests/         # format
mypy src/                       # strict type-check
QT_QPA_PLATFORM=offscreen pytest tests/ -q   # tests (GUI tests run headless)
```

Widget tests run against Qt's `offscreen` platform, so the whole suite passes
with no display server (as it does in CI).

## License

MIT — see [LICENSE](LICENSE).
