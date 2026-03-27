# NekoAgentCore

NekoAgentCore is an Agent OS MVP for structured, evidence-aware task execution.

## Quick start

1. Create and activate a Python 3.12 environment.
2. Install dependencies:

```bash
pip install -e ".[dev]"
```

3. Run tests:

```bash
pytest
```

4. Start a run:

```bash
python -m agent_os.app.cli start-run
```

`start-run` will open interactive prompts for goal and source paths.

## Configuration

- All runtime/model settings are loaded from `config/agent_os.toml`.
- `blueprint.enabled_by_default` controls whether a run enters blueprint mode at start.
- `blueprint.entry_keywords` lets strategist decide whether to route into `Blueprint` for planning-heavy goals.
- `reflection.max_review_loops` and `reflection.min_draft_chars` control reflection retry/evidence escalation.
- You can pass a custom config path with `--config`, for example:

```bash
python -m agent_os.app.cli start-run --config ./config/agent_os.toml
```

## Model provider

- Default provider is `LiteLLM`.
- Provider and model tier mapping are configured in `config/agent_os.toml`.
