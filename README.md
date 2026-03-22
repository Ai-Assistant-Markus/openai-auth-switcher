# OpenAI OAuth Account Switcher

A small, explicit switcher for OpenClaw-style agent setups that use local
`auth-profiles.json` files.

It does one thing:
- keep multiple OpenAI OAuth account snapshots
- switch only when another account is explicitly enabled and available
- refuse to guess

This is designed for teams that hit temporary `rate_limit` or quota issues and
want a safe fallback path instead of manually re-copying auth files.

## What It Solves

- One OpenAI OAuth account gets rate-limited.
- You have a second account, but you do not want hidden silent failover.
- Your agents use local auth snapshots like `~/.openclaw/agents/*/agent/auth-profiles.json`.

The switcher lets you:
- inspect which account is live
- capture the current login state as a named snapshot
- install a chosen snapshot across agents
- auto-switch only when the audit state shows a real rate-limit signal

## Safety Model

This tool is intentionally conservative.

- It never creates OAuth tokens by itself.
- It only installs snapshots you have already captured.
- It only switches to accounts that are both:
  - `enabled: true`
  - not parked via `unavailableUntil`
- It supports `--dry-run`.

## Files

- `openai_auth_switcher.py`
- `registry.example.json`
- `AGENT_INTEGRATION.md`
- `AUTOMATION_EXAMPLE.md`
- `examples/retry_once.sh`

## Assumptions

By default the script assumes:
- OpenClaw root: `~/.openclaw`
- Workspace: `~/.openclaw/workspace`
- Registry: `./registry.local.json` next to the script
- Agents: `main,social,spark`
- Profile name: `openai-codex:default`
- Rate-limit source: `workspace/state/openclaw-capability-audit.json`

All of these are overridable by CLI flags.

## Quick Start

1. Create a local registry file from the example.

```bash
cp registry.example.json registry.local.json
```

2. Authenticate one OpenAI account normally in OpenClaw.

3. Capture that live login as a snapshot.

```bash
python3 openai_auth_switcher.py \
  --registry ./registry.local.json \
  capture-current --email primary@example.com --enable
```

4. Authenticate the second account in OpenClaw.

5. Capture that one too.

```bash
python3 openai_auth_switcher.py \
  --registry ./registry.local.json \
  capture-current --email backup@example.com
```

6. Check current state.

```bash
python3 openai_auth_switcher.py \
  --registry ./registry.local.json \
  status
```

7. Test a manual install.

```bash
python3 openai_auth_switcher.py \
  --registry ./registry.local.json \
  install --email backup@example.com --dry-run
```

8. When ready, run the real install.

```bash
python3 openai_auth_switcher.py \
  --registry ./registry.local.json \
  install --email backup@example.com
```

## Auto-Switch Flow

The `maybe-switch` command looks at the audit JSON and only switches when it
finds a real `rate limit` / `rate_limit` signal in action jobs.

Example:

```bash
python3 openai_auth_switcher.py \
  --registry ./registry.local.json \
  maybe-switch
```

If no enabled backup account is available, it returns a `noop` result instead
of guessing.

See also:
- `AUTOMATION_EXAMPLE.md`
- `examples/retry_once.sh`

## Verify It In Isolation

This package includes an end-to-end verification script that spins up a fake
OpenClaw root, fake auth snapshots, and a fake audit file.

Run it like this:

```bash
python3 tests/verify_publishable_switcher.py
```

It verifies:
- `status`
- `install --dry-run`
- real `install`
- live backup creation before install
- alias resolution
- `maybe-switch` on a real fake `rate_limit` signal

That gives you a clean proof that the public version works without depending on
your personal Markus/OpenClaw state.

## Example Agent Integration

Your main agent can use a rule like:

1. detect `rate_limit` in your audit or cron health file
2. run `maybe-switch`
3. if it reports `install`, retry the affected job once
4. if it reports `noop`, escalate to operator

That keeps the logic explicit:
- switch only on real rate-limit pressure
- retry only once
- no hidden loops

## What You Should Customize

- the registry file
- the list of agent ids
- the audit source path
- the parked/unavailable rules
- the retry policy in your orchestration layer

## What This Does Not Do

- authenticate accounts for you
- mint OAuth tokens
- guarantee provider quota exists
- solve unrelated provider failures
- manage model routing beyond installing auth snapshots

## Do Not Commit

When using this tool in your own setup, make sure you do **not** commit:
- real email addresses
- real snapshot paths
- real auth JSON files
- real state files

Commit only:
- the script
- the example registry
- onboarding docs
- maybe a small demo flow
