#!/usr/bin/env python3
"""Portable OpenAI OAuth account snapshot switcher for OpenClaw-style setups.

This script is intentionally generic:
- no Markus-specific emails
- no hardcoded personal paths in the registry format
- supports dry-run and explicit paths
- only switches when a second snapshot is explicitly enabled and available
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any


DEFAULT_AGENT_IDS = ("main", "social", "spark")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def decode_jwt_payload(token: str) -> dict[str, Any]:
    if not token or token.count(".") < 2:
        return {}
    try:
        payload = token.split(".")[1]
        raw = base64.urlsafe_b64decode(payload + ("=" * (-len(payload) % 4)))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def profile_email(profile_payload: dict[str, Any]) -> str:
    token = str(profile_payload.get("access") or "")
    payload = decode_jwt_payload(token)
    profile = payload.get("https://api.openai.com/profile")
    if isinstance(profile, dict):
        return str(profile.get("email") or "").strip().lower()
    return ""


def profile_expires(profile_payload: dict[str, Any]) -> int:
    try:
        return int(profile_payload.get("expires") or 0)
    except Exception:
        return 0


def account_aliases(account: dict[str, Any], canonical: str) -> list[str]:
    aliases = account.get("aliases") if isinstance(account.get("aliases"), list) else []
    values = [canonical.strip().lower()]
    for alias in aliases:
        alias_value = str(alias).strip().lower()
        if alias_value and alias_value not in values:
            values.append(alias_value)
    return values


def resolve_account_key(accounts: dict[str, Any], email: str) -> str:
    lookup = str(email or "").strip().lower()
    for canonical, account in accounts.items():
        if not isinstance(account, dict):
            continue
        if lookup in account_aliases(account, canonical):
            return canonical
    return ""


def agent_auth_path(root: Path, agent_id: str) -> Path:
    return root / "agents" / agent_id / "agent" / "auth-profiles.json"


def current_profiles(root: Path, profile_name: str, agent_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    current: dict[str, dict[str, Any]] = {}
    for agent_id in agent_ids:
        data = load_json(agent_auth_path(root, agent_id))
        profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
        profile_payload = profiles.get(profile_name) if isinstance(profiles, dict) else {}
        if isinstance(profile_payload, dict):
            current[agent_id] = profile_payload
    return current


def current_email(root: Path, profile_name: str, agent_ids: tuple[str, ...]) -> str:
    profiles = current_profiles(root, profile_name, agent_ids)
    for agent_id in agent_ids:
        email = profile_email(profiles.get(agent_id, {}))
        if email:
            return email
    return ""


def account_available(account: dict[str, Any], agent_ids: tuple[str, ...]) -> tuple[bool, str]:
    if not bool(account.get("enabled", False)):
        return (False, "disabled")
    unavailable_until = str(account.get("unavailableUntil") or "").strip()
    if unavailable_until and unavailable_until > date.today().isoformat():
        return (False, f"parked_until_{unavailable_until}")
    snapshots = account.get("snapshots") if isinstance(account.get("snapshots"), dict) else {}
    missing = [agent_id for agent_id in agent_ids if not str(snapshots.get(agent_id) or "").strip()]
    if missing:
        return (False, f"missing_snapshot:{','.join(missing)}")
    for agent_id in agent_ids:
        if not Path(str(snapshots.get(agent_id))).expanduser().exists():
            return (False, f"missing_file:{agent_id}")
    return (True, "")


def detect_rate_limit_from_audit(audit_path: Path) -> tuple[bool, str]:
    capability = load_json(audit_path)
    cron = capability.get("cron") if isinstance(capability.get("cron"), dict) else {}
    action_jobs = cron.get("actionJobs") if isinstance(cron.get("actionJobs"), list) else []
    for job in action_jobs:
        if not isinstance(job, dict):
            continue
        error = str(job.get("lastError") or "").lower()
        if "rate limit" in error or "rate_limit" in error:
            return (True, str(job.get("name") or "unknown_job"))
    return (False, "")


def install_account(
    *,
    root: Path,
    registry_path: Path,
    state_path: Path,
    backup_dir: Path,
    registry: dict[str, Any],
    email: str,
    agent_ids: tuple[str, ...],
    profile_name: str,
    dry_run: bool,
) -> dict[str, Any]:
    accounts = registry.get("accounts") if isinstance(registry.get("accounts"), dict) else {}
    canonical = resolve_account_key(accounts, email)
    account = accounts.get(canonical)
    if not isinstance(account, dict):
        raise SystemExit(f"Unknown account: {email}")
    available, reason = account_available(account, agent_ids)
    if not available:
        raise SystemExit(f"Account not installable: {canonical or email} ({reason})")
    snapshots = account.get("snapshots") if isinstance(account.get("snapshots"), dict) else {}
    installed: list[str] = []
    live_backups: dict[str, str] = {}
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    for agent_id in agent_ids:
        src = Path(str(snapshots.get(agent_id))).expanduser()
        dst = agent_auth_path(root, agent_id)
        installed.append(agent_id)
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                backup_path = backup_dir / f"{agent_id}-auth-profiles.live-before-install.{timestamp}.json"
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, backup_path)
                live_backups[agent_id] = str(backup_path)
            shutil.copy2(src, dst)
    if not dry_run:
        registry["activeAccount"] = canonical
        registry["lastInstalledAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        write_json(registry_path, registry)
    payload = {
        "status": "ok",
        "action": "install",
        "installedAccount": canonical,
        "installedAgents": installed,
        "liveBackups": live_backups,
        "profileName": profile_name,
        "dryRun": dry_run,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    write_json(state_path, payload)
    return payload


def capture_current(
    *,
    root: Path,
    registry_path: Path,
    state_path: Path,
    backup_dir: Path,
    registry: dict[str, Any],
    email: str,
    agent_ids: tuple[str, ...],
    profile_name: str,
    enable: bool,
    dry_run: bool,
) -> dict[str, Any]:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    safe_name = email.replace("@", "_at_").replace(".", "_")
    account_snapshots: dict[str, str] = {}
    for agent_id in agent_ids:
        src = agent_auth_path(root, agent_id)
        dst = backup_dir / f"{agent_id}-auth-profiles.{safe_name}.{timestamp}.json"
        account_snapshots[agent_id] = str(dst)
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    accounts = registry.setdefault("accounts", {})
    canonical = resolve_account_key(accounts, email) or email
    existing = accounts.get(canonical) if isinstance(accounts.get(canonical), dict) else {}
    aliases = existing.get("aliases", []) if isinstance(existing.get("aliases"), list) else []
    account_payload = {
        "enabled": enable,
        "provider": "openai-codex",
        "notes": "Captured from current live auth state.",
        "capturedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "snapshots": account_snapshots,
        "aliases": aliases,
    }
    if not dry_run:
        accounts[canonical] = account_payload
        live_email = current_email(root, profile_name, agent_ids)
        if live_email in account_aliases(account_payload, canonical):
            registry["activeAccount"] = canonical
        write_json(registry_path, registry)
    payload = {
        "status": "ok",
        "action": "capture-current",
        "capturedAccount": canonical,
        "profileName": profile_name,
        "enabled": enable,
        "dryRun": dry_run,
        "snapshots": account_snapshots,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    write_json(state_path, payload)
    return payload


def build_status(
    *,
    root: Path,
    registry: dict[str, Any],
    audit_path: Path,
    profile_name: str,
    agent_ids: tuple[str, ...],
) -> dict[str, Any]:
    live_email = current_email(root, profile_name, agent_ids)
    accounts = registry.get("accounts") if isinstance(registry.get("accounts"), dict) else {}
    account_status: list[dict[str, Any]] = []
    for email, account in accounts.items():
        if not isinstance(account, dict):
            continue
        available, reason = account_available(account, agent_ids)
        aliases = account_aliases(account, email)
        account_status.append(
            {
                "email": email,
                "aliases": aliases[1:],
                "enabled": bool(account.get("enabled", False)),
                "available": available,
                "availabilityReason": reason,
                "unavailableUntil": str(account.get("unavailableUntil") or ""),
                "isActive": live_email in aliases,
            }
        )
    per_agent: list[dict[str, Any]] = []
    live_profiles = current_profiles(root, profile_name, agent_ids)
    for agent_id in agent_ids:
        profile_payload = live_profiles.get(agent_id, {})
        per_agent.append(
            {
                "agentId": agent_id,
                "email": profile_email(profile_payload),
                "expires": profile_expires(profile_payload),
            }
        )
    rate_limit, source = detect_rate_limit_from_audit(audit_path)
    return {
        "status": "ok",
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "activeAccount": live_email,
        "profileName": profile_name,
        "accounts": account_status,
        "agents": per_agent,
        "rateLimitDetected": rate_limit,
        "rateLimitSource": source,
    }


def maybe_switch(
    *,
    root: Path,
    registry_path: Path,
    state_path: Path,
    backup_dir: Path,
    registry: dict[str, Any],
    audit_path: Path,
    profile_name: str,
    agent_ids: tuple[str, ...],
    dry_run: bool,
) -> dict[str, Any]:
    live_email = current_email(root, profile_name, agent_ids)
    rate_limit, source = detect_rate_limit_from_audit(audit_path)
    if not rate_limit:
        payload = {
            "status": "noop",
            "reason": "no_rate_limit_detected",
            "activeAccount": live_email,
            "profileName": profile_name,
            "dryRun": dry_run,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        write_json(state_path, payload)
        return payload
    accounts = registry.get("accounts") if isinstance(registry.get("accounts"), dict) else {}
    for email, account in accounts.items():
        if not isinstance(account, dict):
            continue
        if live_email in account_aliases(account, email):
            continue
        available, _ = account_available(account, agent_ids)
        if available:
            payload = install_account(
                root=root,
                registry_path=registry_path,
                state_path=state_path,
                backup_dir=backup_dir,
                registry=registry,
                email=email,
                agent_ids=agent_ids,
                profile_name=profile_name,
                dry_run=dry_run,
            )
            payload["switchReason"] = "rate_limit"
            payload["rateLimitSource"] = source
            write_json(state_path, payload)
            return payload
    payload = {
        "status": "noop",
        "reason": "rate_limit_detected_but_no_alternate_account_available",
        "activeAccount": live_email,
        "profileName": profile_name,
        "dryRun": dry_run,
        "rateLimitSource": source,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    write_json(state_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Switch OpenAI OAuth auth snapshots safely.")
    parser.add_argument("--root", default=str(Path.home() / ".openclaw"))
    parser.add_argument("--workspace", default="")
    parser.add_argument("--registry", default="")
    parser.add_argument("--state", default="")
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--audit", default="")
    parser.add_argument("--profile-name", default="openai-codex:default")
    parser.add_argument("--agents", default="main,social,spark")
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    install_parser = sub.add_parser("install")
    install_parser.add_argument("--email", required=True)

    capture_parser = sub.add_parser("capture-current")
    capture_parser.add_argument("--email", required=True)
    capture_parser.add_argument("--enable", action="store_true")

    sub.add_parser("maybe-switch")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser()
    workspace = Path(args.workspace).expanduser() if args.workspace else root / "workspace"
    package_dir = Path(__file__).resolve().parent
    registry_path = Path(args.registry).expanduser() if args.registry else package_dir / "registry.local.json"
    state_path = Path(args.state).expanduser() if args.state else workspace / "state" / "openai-auth-switcher.json"
    backup_dir = Path(args.backup_dir).expanduser() if args.backup_dir else workspace / "state" / "openai-auth-backups"
    audit_path = Path(args.audit).expanduser() if args.audit else workspace / "state" / "openclaw-capability-audit.json"
    agent_ids = tuple(item.strip() for item in str(args.agents).split(",") if item.strip()) or DEFAULT_AGENT_IDS

    registry = load_json(registry_path)
    if not registry:
        raise SystemExit(f"Registry missing or invalid: {registry_path}")

    if args.command == "status":
        payload = build_status(
            root=root,
            registry=registry,
            audit_path=audit_path,
            profile_name=args.profile_name,
            agent_ids=agent_ids,
        )
    elif args.command == "install":
        payload = install_account(
            root=root,
            registry_path=registry_path,
            state_path=state_path,
            backup_dir=backup_dir,
            registry=registry,
            email=args.email.strip().lower(),
            agent_ids=agent_ids,
            profile_name=args.profile_name,
            dry_run=args.dry_run,
        )
    elif args.command == "capture-current":
        payload = capture_current(
            root=root,
            registry_path=registry_path,
            state_path=state_path,
            backup_dir=backup_dir,
            registry=registry,
            email=args.email.strip().lower(),
            agent_ids=agent_ids,
            profile_name=args.profile_name,
            enable=bool(args.enable),
            dry_run=args.dry_run,
        )
    else:
        payload = maybe_switch(
            root=root,
            registry_path=registry_path,
            state_path=state_path,
            backup_dir=backup_dir,
            registry=registry,
            audit_path=audit_path,
            profile_name=args.profile_name,
            agent_ids=agent_ids,
            dry_run=args.dry_run,
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
