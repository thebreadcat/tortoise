#!/usr/bin/env bash
# Merge GitHub's initial commit (often GPL-3.0) with local Tortoise (MIT), then push.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Fetching origin..."
if ! git fetch origin; then
  echo ""
  echo "Fetch failed. Fix GitHub access first:"
  echo "  SSH:  ssh -T git@github.com   (add key to github.com/settings/keys)"
  echo "  HTTPS: git remote set-url origin https://github.com/thebreadcat/tortoise.git"
  echo "         gh auth login"
  exit 1
fi

if git merge-base --is-ancestor origin/main main 2>/dev/null; then
  echo "==> Already up to date with origin/main; pushing..."
  git push -u origin main
  exit 0
fi

echo "==> Merging unrelated histories (keep local MIT LICENSE)..."
if ! git pull origin main --allow-unrelated-histories --no-edit; then
  if git status --porcelain | grep -q '^UU.*LICENSE'; then
    git checkout --ours LICENSE
    git add LICENSE
    git commit -m "Merge GitHub initial commit; keep MIT license"
  else
    echo "Merge failed. Resolve conflicts manually, then: git push -u origin main"
    exit 1
  fi
fi

echo "==> Pushing main..."
git push -u origin main
echo ""
echo "Done. On GitHub: Settings → General → License → MIT (if the badge still shows GPL)."
