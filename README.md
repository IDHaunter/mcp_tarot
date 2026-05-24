# MCP Tarot

Tarot fortune telling with a **Python MCP server** (deck + card data tools) and an **interactive client** that uses an OpenAI-compatible LLM (vLLM, Ollama, etc.) to interpret readings.

## Requirements

- Python 3.11+
- API key for your LLM endpoint (if required)

## Install

```bash
cd mcp_tarot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -e .
```

## Configuration

Copy and edit the example config:

```bash
copy config\client.example.yaml config\client.yaml
```

Set `llm.base_url`, `llm.model`, and either `llm.api_key` or the `OPENAI_API_KEY` environment variable.
You can override the API URL with the `LLM_BASE_URL` environment variable.
If the LLM is unreachable, the bot prints an error and continues instead of crashing.

### Logging

In `config/client.yaml`:

```yaml
logging:
  level: INFO   # DEBUG | INFO | WARNING | ERROR | CRITICAL
  file: logs/client.log
```

Logs append to a single file (no rotation by date). Format: date/time, level, module (`client.bot`, …), message.
At `DEBUG`, all main dialog and MCP/LLM steps are recorded. Override level with `LOG_LEVEL` env var.

## Run the client (bot)

From the project root:

```bash
python -m client
# or
python -m client -c config/client.yaml
```

### User flow

1. Welcome message — ask your question.
2. The bot shuffles the deck via MCP (cards are **not** shown).
3. Choose card **positions** in the deck (e.g. `3, 17, 42`; three cards recommended).
4. The bot loads interpretations and pair relations, then the LLM delivers the reading.
5. Optionally enter another **position** (1–78) for a clarification card.
6. Start a new topic or type `quit` to exit.

## Run the MCP server alone

The server uses stdio transport (for MCP hosts or the client subprocess):

```bash
python -m server
```

### Tools

| Tool | Description |
|------|-------------|
| `generate_tarot_sequence` | Shuffled 78-card deck with upright/reversed flags |
| `get_card_information` | Card JSON + pairwise `relations` for drawn cards |
| `get_additional_card` | One card by deck position + influences vs. cards already drawn |

Card data lives under `server/data/` (`major/`, `minor/{cups,pentacles,swords,wands}/`).

Smoke test (no LLM): `python scripts/test_mcp_tools.py`

### Unit tests (server)

```bash
pip install -e ".[dev]"
pytest
```

Covers `server/deck.py`, `server/card_store.py`, and `server/relations.py`.

## Architecture

```
mcp_tarot/
├── config/
│   ├── client.yaml          # runtime settings (LLM + MCP)
│   └── client.example.yaml
├── server/                  # MCP server (stdio)
│   ├── app.py               # 3 MCP tools
│   ├── deck.py              # generate_tarot_sequence()
│   ├── card_store.py        # load major/minor JSON
│   ├── relations.py         # pair_dependencies()
│   └── data/                # 78 card JSON files
│      ├── major/            # 22 major cards JSONs
│      ├── minor/            # 14x4 minor cards JSONs
│         ├── cups/          
│         ├── pentacles/
│         ├── swords/
│         ├── wands/
├── client/                  # interactive bot
│   ├── bot.py               # user conversation flow
│   ├── llm.py               # OpenAI-compatible API
│   ├── mcp_session.py       # MCP stdio client
│   └── config.py            # settings loader (YAML → Pydantic)
└── pyproject.toml
```
