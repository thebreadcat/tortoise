# Tortoise

Chunk-based coding harness for slow or small local LLMs (Ollama, LM Studio, LiteLLM, OpenAI-compatible APIs).

Tortoise breaks work into atomic steps with a persistent **BRAIN**, **TODO** queue, backups, and HTML validation — so models that struggle with large files can still ship working code one chunk at a time.

**Zero dependencies** — Python 3.10+ stdlib only.

## Quick start

```bash
git clone https://github.com/thebreadcat/tortoise.git
cd tortoise

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
- See [SECURITY.md](SECURITY.md) for details.

The repo ships `config.example.json` only (`api_key: null`). Real keys stay in each project's `.tortoise/config.json` (gitignored by `tortoise init`).

## Used by

[Workshop](https://github.com/thebreadcat/workshop) — natural-language app builder that drives Tortoise in a loop.

Workshop does not bundle Tortoise. Install side by side or as a submodule:

```bash
git clone https://github.com/thebreadcat/workshop.git
cd workshop
git submodule add https://github.com/thebreadcat/tortoise.git vendor/tortoise
```

Workshop finds `vendor/tortoise/tortoise.py` or `../tortoise/tortoise.py`. Override with:

```bash
export TORTOISE_PATH=/path/to/tortoise/tortoise.py
```

## Publishing to GitHub

If you created the repo on GitHub with a **GPL-3.0** license template, the remote has one commit and your local clone has another. `git push` fails with *unrelated histories* or *non-fast-forward* — merge or replace the remote history, then push. Set **Settings → General → License → Other** if the badge still shows GPL.

## License

[Tortoise License](LICENSE) — free to use, modify, and share, but you may not sell the software or offer paid support for it. Not OSI-approved open source. You may still use Tortoise in commercial projects (e.g. apps you build with it).
