# Agent Integration

This tool works best when the agent treats it as a narrow safety utility, not a
general routing engine.

## Recommended Integration Contract

Use the switcher only when all of these are true:

1. the current failure is clearly `rate_limit` or quota-related
2. the affected path actually uses the swappable OpenAI OAuth auth store
3. an alternate account is explicitly enabled in the registry
4. the job is worth retrying once

## Suggested Runtime Flow

1. Read your audit or cron health file.
2. If the failure is not `rate_limit`, do not call the switcher.
3. Run:

```bash
python3 openai_auth_switcher.py --registry ./registry.local.json maybe-switch
```

4. If result is `install`, retry the failed task once.
5. If result is `noop`, escalate to operator.

If you want a minimal shell wrapper for this exact pattern, see:

- `AUTOMATION_EXAMPLE.md`
- `examples/retry_once.sh`

## Suggested Agent Policy Snippet

You can adapt the following into your agent docs or playbook:

```text
If a publish-adjacent or support job fails with a real OpenAI rate-limit signal,
use the OpenAI OAuth Account Switcher as a bounded safety tool.

Rules:
- Only switch on clear rate-limit or quota pressure.
- Never switch for model_not_found, auth misconfiguration, parsing errors, or bad prompts.
- Retry the affected job at most once after a successful switch.
- If no alternate account is available, escalate instead of looping.
- Do not silently enable parked accounts.
```

## Good Use Cases

- background research jobs
- long-form generation
- support optimization jobs
- non-destructive retryable tasks

## Bad Use Cases

- unknown failures
- broken auth state
- wrong model selection
- provider-specific outages unrelated to quota
- repeated automatic retry loops

## Operational Tip

Keep your primary account dedicated to more important paths and use the backup
account mostly for background or support lanes. That reduces surprise switches
on your highest-value jobs.
