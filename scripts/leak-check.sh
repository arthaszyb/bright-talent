#!/usr/bin/env bash
# Leak check: fail if any internal-company reference appears in the target tree.
# Usage: leak-check.sh <dir> [more dirs...]   (exit 0 = clean, 1 = leaks found)
set -u
targets=("${@:-.}")

# Red-line patterns (case-insensitive). Grouped: brand, internal platforms,
# internal domains/hosts, email domains, credential shapes, internal doc ids.
patterns=(
  'shopee' 'garena' 'seatalk' 'sea group'
  '\bswp\b' '\bdems\b' '\bsmc\b' 'cmdb' 'space\.shopee' 'spacemcp' 'space-mcp'
  'cachecloud' 'bromo' '\becp\b' '\beks\b.*cluster' 'mkp[-_ ]buyer'
  'git\.garena\.com' 'confluence\.shopee' '\.shopee\.io' 'pypi\.shopee'
  '@shopee\.com' '@garena\.com'
  '\bdesre\b' '\bde-sre\b' 'space_user_token' 'seatalk_app' 'dod_team' '\baiops\b'
  'sk-ant-[A-Za-z0-9_-]{10,}' 'glpat-[A-Za-z0-9_-]{10,}' 'ghp_[A-Za-z0-9]{20,}'
  'AKIA[A-Z0-9]{12,}' 'sk-[A-Za-z0-9]{20,}'
  'pageId=[0-9]{6,}'
)

fail=0
for pat in "${patterns[@]}"; do
  # Exclude this script itself, .git internals, and third-party/dev artifacts
  # (virtualenvs, caches, lockfiles) that are never shipped.
  hits=$(grep -rInE --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude='leak-check.sh' --exclude='uv.lock' -i -- "$pat" "${targets[@]}" 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "LEAK [$pat]:"
    echo "$hits"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "leak-check: clean"
fi
exit "$fail"
