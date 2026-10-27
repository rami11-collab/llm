#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
if [[ ! -x "$project_root/.venv/bin/python" ]]; then
  echo "First run: bash scripts/setup_codespaces.sh" >&2
  exit 1
fi
exec "$project_root/.venv/bin/python" "$script_dir/codespaces.py" start "$@"
