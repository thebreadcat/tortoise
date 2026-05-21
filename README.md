# Tortoise

Chunk-based coding harness for slow or small local LLMs (Ollama, LM Studio, LiteLLM, OpenAI-compatible APIs).

Tortoise breaks work into atomic steps with a persistent **BRAIN**, **TODO** queue, backups, and HTML validation — so models that struggle with large files can still ship working code one chunk at a time.

**Zero dependencies** — Python 3.10+ stdlib only.

## Quick start

```bash
git clone https://github.com/thebreadcat/tortoise.git
cd tortoise

# If tortoise.py is missing (stub only), sync from Workshop repo:
python3 sync_from_workshop.py
# Or: python3 scripts/bootstrap_copy.py

# Before publishing to GitHub — scan for secrets:
chmod +x scripts/check-secrets.sh
./scripts/check-secrets.sh

# In your app or repo:
cd /path/to/your-project
python3 /path/to/tortoise/tortoise.py init
python3 /path/to/tortoise/tortoise.py config --endpoint http://localhost:11434/v1 --model phi3
python3 /path/to/tortoise/tortoise.py add "Create index.html skeleton"
python3 /path/to/tortoise/tortoise.py run --yes
```

`init` creates `.tortoise/` and adds **`.tortoise/config.json` to `.gitignore`** so API keys never get committed by mistake.

## Commands

| Command | Description |
|---------|-------------|
| `init` | Create `.tortoise/` (BRAIN, TODO, config) |
| `config` | Show or set endpoint, model, api_key |
| `add "task"` | Queue a chunk task |
| `plan "goal"` | Ask the model to split a goal into tasks |
| `run` | Execute the next chunk |
| `run --yes` | Run without write confirmation |
| `resume` | Continue after an interrupted chunk |
| `status` | Show queue and config |
| `rollback` | Restore last backup |

## Configuration

Copy the example (no secrets):

```bash
cp config.example.json .tortoise/config.json
```

Set your endpoint and model:

```bash
tortoise config --endpoint http://localhost:11434/v1 --model qwen2.5-coder
```

Optional API key (stored **only** in `.tortoise/config.json`, gitignored):

```bash
tortoise config --api-key sk-...
```

## Security

- **Never commit** `.tortoise/config.json` — it may contain `api_key`.
- Run `./scripts/check-secrets.sh` before pushing this repo or your app.
- See [SECURITY.md](SECURITY.md) for details.

## Publishing to GitHub

1. Clone **both** repos side by side (`tortoise/` and `workforce-tortise/`).
2. Run `python3 sync_from_workshop.py` — writes the full `tortoise.py` (replaces the dev launcher).
3. Run `./scripts/check-secrets.sh` — must pass before you push.
4. `git add` and push. Never commit `.tortoise/config.json` from your apps.

The repo ships `config.example.json` only (`api_key: null`). Real keys stay in each project's `.tortoise/config.json` (gitignored by `tortoise init`).

## Used by

[Workshop](../workforce-tortise) — natural-language app builder that drives Tortoise in a loop.

With both repos cloned side by side, Workshop finds `../tortoise/tortoise.py` automatically.

```bash
export TORTOISE_PATH=/path/to/tortoise/tortoise.py   # optional override
```

## Publishing to GitHub

If you created the repo on GitHub with a **GPL-3.0** license template, the remote has one commit and your local clone has another (MIT). `git push` fails with *unrelated histories* or *non-fast-forward* — that is a history mismatch, not a missing license file.

From this repo (after `python3 sync_from_workshop.py` and `./scripts/check-secrets.sh`):

```bash
chmod +x scripts/publish-to-github.sh
./scripts/publish-to-github.sh
```

That merges histories and keeps **MIT** `LICENSE`. If you only want your local tree on GitHub and do not need the template commit:

```bash
git push -u origin main --force
```

Then set **Settings → General → License → MIT** on GitHub if the badge still shows GPL.

## License

MIT — see [LICENSE](LICENSE).
