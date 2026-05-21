#!/usr/bin/env bash
# Scan tracked files for common secret patterns. Run before git push.
set -euo pipefail
cd "$(dirname "$0")/.."

if git rev-parse --is-inside-work-tree &>/dev/null; then
  TRACKED=$(git ls-files)
else
  TRACKED=$(find . -type f \
    ! -path './.git/*' ! -path './.venv/*' ! -path './venv/*' \
    -name '*.py' -o -name '*.json' -o -name '*.md' -o -name '*.yml' 2>/dev/null | head -200)
fi

FAIL=0
PATTERNS=(
  'sk-[a-zA-Z0-9]{20,}'
  'api_key["\s:]+["\x27][^"\x27nul][^"\x27]+["\x27]'
  'Bearer [a-zA-Z0-9._-]{20,}'
  'password["\s:]+["\x27][^"\x27]+["\x27]'
)

echo "Checking for secret patterns in repository files…"

while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  [[ "$f" == *config.example.json* ]] && continue
  for pat in "${PATTERNS[@]}"; do
    if grep -qE "$pat" "$f" 2>/dev/null; then
      echo "  FAIL: possible secret in $f (pattern: $pat)"
      FAIL=1
    fi
  done
done <<< "$TRACKED"

if [[ -f .tortoise/config.json ]]; then
  echo "  NOTE: .tortoise/config.json exists locally (should stay untracked)."
fi

if [[ $FAIL -eq 0 ]]; then
  echo "  OK — no obvious secrets in tracked files."
  exit 0
fi
echo "  Fix issues before publishing."
exit 1
