#!/usr/bin/env bash
set -euo pipefail

# Example wrapper:
# - run a job
# - if it fails with rate-limit pressure already reflected in the audit file,
#   ask the switcher to try one bounded account swap
# - retry the job exactly once
#
# Usage:
#   ./examples/retry_once.sh python3 your_job.py --arg value

ROOT_PATH="${OPENCLAW_ROOT:-$HOME/.openclaw}"
WORKSPACE_PATH="${OPENCLAW_WORKSPACE:-$ROOT_PATH/workspace}"
REGISTRY_PATH="${OPENAI_SWITCHER_REGISTRY:-$(pwd)/registry.local.json}"
SWITCHER_PATH="${OPENAI_SWITCHER_PATH:-$(pwd)/openai_auth_switcher.py}"

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <job command> [args...]" >&2
  exit 64
fi

run_job() {
  "$@"
}

if run_job "$@"; then
  echo "job_ok"
  exit 0
fi

switch_json="$(
  python3 "$SWITCHER_PATH" \
    --root "$ROOT_PATH" \
    --workspace "$WORKSPACE_PATH" \
    --registry "$REGISTRY_PATH" \
    maybe-switch
)"

echo "$switch_json"

switch_status="$(printf '%s' "$switch_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))')"

if [ "$switch_status" != "ok" ]; then
  echo "switcher_noop_or_error"
  exit 1
fi

echo "retrying_job_once_after_switch"
run_job "$@"
