# Release Checklist

Before publishing this package:

1. Run the isolated verification:
   `python3 tests/verify_publishable_switcher.py`
2. Confirm there is no `registry.local.json` in the repo.
3. Confirm there are no live auth snapshots or backup files in the repo.
4. Grep for personal emails, local usernames, and absolute private paths.
5. Re-read the README and AGENT_INTEGRATION docs for generic wording.
6. Only publish from this `public-releases` copy, never from the Markus runtime folder.

Quick grep:

```bash
rg -n "(@gmail|/Users/|ai-assistent-markus|markus_openai|registry.local|live-before-install)" .
```
