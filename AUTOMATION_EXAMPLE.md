# Automation Example

This repo is intentionally not a scheduler by itself.

It is meant to be called by an agent, wrapper script, cron job, or runtime
supervisor when a real `rate_limit` signal has already been detected.

## Included Example

- `examples/retry_once.sh`

That wrapper demonstrates the intended pattern:

1. run a job normally
2. if the job fails, call `maybe-switch`
3. only continue if the switcher reports a real install
4. retry the job exactly once

## Why This Matters

This keeps the automation bounded:

- no silent looping
- no repeated retries
- no switching on unrelated failures
- no automatic enabling of parked accounts

## Typical Use Cases

- long-form generation
- research jobs
- retryable support workflows
- non-destructive content tooling

## Not Recommended

- unknown failures
- auth corruption
- provider outages unrelated to quota
- repeated background retry loops
