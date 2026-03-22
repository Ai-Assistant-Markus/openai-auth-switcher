#!/usr/bin/env python3
"""End-to-end verification for the publishable OpenAI auth switcher.

This test creates an isolated fake OpenClaw root, fake auth snapshots, and a
fake audit file, then exercises the public CLI exactly the way a GitHub user
would.
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "openai_auth_switcher.py"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def fake_access_token(email: str) -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "https://api.openai.com/profile": {
            "email": email,
        }
    }
    return f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}.signature"


def auth_profiles_payload(email: str, expires: int = 1893456000) -> dict:
    return {
        "profiles": {
            "openai-codex:default": {
                "access": fake_access_token(email),
                "expires": expires,
            }
        }
    }


def run_cli(*args: str) -> dict:
    command = ["python3", str(SCRIPT_PATH), *args]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="openai-auth-switcher-test-") as temp_dir:
        sandbox = Path(temp_dir)
        root = sandbox / ".openclaw"
        workspace = root / "workspace"
        registry = sandbox / "registry.local.json"
        state = sandbox / "state" / "openai-auth-switcher.json"
        backup_dir = sandbox / "backups"
        audit = workspace / "state" / "openclaw-capability-audit.json"
        snapshots_dir = sandbox / "snapshots"
        agents = ("main", "social", "spark")

        for agent in agents:
            live_path = root / "agents" / agent / "agent" / "auth-profiles.json"
            write_json(live_path, auth_profiles_payload("primary@example.com"))

            primary_snapshot = snapshots_dir / f"{agent}.primary.json"
            backup_snapshot = snapshots_dir / f"{agent}.backup.json"
            write_json(primary_snapshot, auth_profiles_payload("primary@example.com"))
            write_json(backup_snapshot, auth_profiles_payload("backup@example.com"))

        write_json(
            registry,
            {
                "version": 1,
                "provider": "openai-codex",
                "activeAccount": "primary@example.com",
                "accounts": {
                    "primary@example.com": {
                        "enabled": True,
                        "provider": "openai-codex",
                        "notes": "Primary account.",
                        "snapshots": {
                            agent: str(snapshots_dir / f"{agent}.primary.json") for agent in agents
                        },
                    },
                    "backup@example.com": {
                        "enabled": True,
                        "provider": "openai-codex",
                        "notes": "Backup account.",
                        "aliases": ["backup+alt@example.com"],
                        "snapshots": {
                            agent: str(snapshots_dir / f"{agent}.backup.json") for agent in agents
                        },
                    },
                },
            },
        )

        write_json(audit, {"cron": {"actionJobs": []}})

        common_args = (
            "--root",
            str(root),
            "--workspace",
            str(workspace),
            "--registry",
            str(registry),
            "--state",
            str(state),
            "--backup-dir",
            str(backup_dir),
            "--audit",
            str(audit),
        )

        status_before = run_cli(*common_args, "status")
        assert status_before["activeAccount"] == "primary@example.com", status_before
        assert status_before["rateLimitDetected"] is False, status_before

        install_dry = run_cli(*common_args, "--dry-run", "install", "--email", "backup+alt@example.com")
        assert install_dry["status"] == "ok", install_dry
        assert install_dry["installedAccount"] == "backup@example.com", install_dry
        assert install_dry["dryRun"] is True, install_dry

        install_real = run_cli(*common_args, "install", "--email", "backup@example.com")
        assert install_real["status"] == "ok", install_real
        assert install_real["installedAccount"] == "backup@example.com", install_real
        assert all((backup_dir / Path(path).name).exists() for path in install_real["liveBackups"].values()), install_real

        status_after_install = run_cli(*common_args, "status")
        assert status_after_install["activeAccount"] == "backup@example.com", status_after_install

        for agent in agents:
            live_data = json.loads((root / "agents" / agent / "agent" / "auth-profiles.json").read_text(encoding="utf-8"))
            live_profile = live_data["profiles"]["openai-codex:default"]
            payload = live_profile["access"].split(".")[1]
            decoded = json.loads(base64.urlsafe_b64decode(payload + ("=" * (-len(payload) % 4))).decode("utf-8"))
            assert decoded["https://api.openai.com/profile"]["email"] == "backup@example.com"

        write_json(
            audit,
            {
                "cron": {
                    "actionJobs": [
                        {
                            "name": "Long-form generator",
                            "lastError": "API rate limit reached. Please try again later. (rate_limit)",
                        }
                    ]
                }
            },
        )

        maybe_switch = run_cli(*common_args, "maybe-switch")
        assert maybe_switch["status"] == "ok", maybe_switch
        assert maybe_switch["installedAccount"] == "primary@example.com", maybe_switch
        assert maybe_switch["switchReason"] == "rate_limit", maybe_switch

        final_status = run_cli(*common_args, "status")
        assert final_status["activeAccount"] == "primary@example.com", final_status
        assert final_status["rateLimitDetected"] is True, final_status

        print(
            json.dumps(
                {
                    "status": "ok",
                    "verified": [
                        "status",
                        "install_dry_run",
                        "install_real",
                        "live_backup_before_install",
                        "alias_resolution",
                        "rate_limit_maybe_switch",
                    ],
                    "sandbox": str(sandbox),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
