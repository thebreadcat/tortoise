# Security

## What must never be committed

- `.tortoise/config.json` in any project using Tortoise (may contain `api_key`)
- API keys, tokens, passwords, or private endpoint URLs with embedded credentials
- Files under `.tortoise/backups/` (copies of your source tree)

This repository ships only `config.example.json` with `api_key` set to `null`.

## Safe setup

```bash
tortoise init
tortoise config --endpoint http://localhost:11434/v1 --model your-model
# Optional — stored only in .tortoise/config.json (gitignored by init):
tortoise config --api-key YOUR_KEY
```

Or copy the example:

```bash
mkdir -p .tortoise
cp config.example.json .tortoise/config.json
```

## Before pushing to GitHub

From the Tortoise repo root:

```bash
./scripts/check-secrets.sh
```

From a project that uses Tortoise:

```bash
git status   # ensure .tortoise/config.json is not staged
```

## Reporting

If you find a security issue, open a private report with the maintainer rather than a public issue.
