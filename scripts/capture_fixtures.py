"""Capture real responses as test fixtures, with the identifying bits removed.

Hand-written fixtures encode what the author BELIEVED the API returns, which is
the same mistake as a hand-written type: the first draft of this repo's tests
invented response bodies and three of them were missing required fields the real
API always sends. Captured fixtures cannot make that mistake.

What is redacted is only what identifies a person or an account -- names, email
addresses, user ids, the key's own prefix. Shape, nulls and field order are left
exactly as they arrived, because those are the parts being tested.

    GALILEO_API_KEY=gk_... uv run python scripts/capture_fixtures.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures"
BASE = os.environ.get("GALILEO_BASE_URL", "https://api-dev.physionlabs.ai").rstrip("/")
KEY = os.environ["GALILEO_API_KEY"]

REDACT = {
    "id": None,          # only at the top level of an account; see below
    "email": "someone@example.com",
    "name": "Example Name",
    "prefix": "gk_live_xxxx",
    "last4": "xxxx",
}


def redact_account(account: dict) -> dict:
    out = dict(account)
    out["id"] = "user_EXAMPLE"
    out["email"] = REDACT["email"]
    out["name"] = REDACT["name"]
    if isinstance(out.get("api_key"), dict):
        out["api_key"] = {
            **out["api_key"],
            "prefix": REDACT["prefix"],
            "last4": REDACT["last4"],
        }
    return out


def redact_urls(node: object) -> object:
    """Point every video URL at example.com.

    Not because a public CDN URL is a secret, but because the real ones name an
    internal host and show the key layout we use inside the bucket -- and a
    fixture in a public repository is published, permanently, to anyone who
    clones it. The shape is what the tests need; the host is not.
    """
    if isinstance(node, dict):
        return {k: (_example_url(v) if _is_url_key(k, v) else redact_urls(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [redact_urls(v) for v in node]
    return node


def _is_url_key(key: str, value: object) -> bool:
    return isinstance(value, str) and (key.endswith("_url") or key == "url") and "://" in value


def _example_url(value: str) -> str:
    tail = value.rsplit("/", 1)[-1]
    return f"https://cdn.example.com/{tail}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"authorization": f"Bearer {KEY}"}, timeout=30) as client:
        cases = {
            "status.json": ("/v1/status", None),
            "account.json": ("/v1/me", redact_account),
            "models.json": ("/v1/models", None),
            "quota.json": ("/v1/quota", None),
            "credits.json": ("/v1/credits", None),
        }
        for filename, (path, transform) in cases.items():
            body = client.get(f"{BASE}{path}").raise_for_status().json()
            if transform:
                body = transform(body)
            (OUT / filename).write_text(json.dumps(body, indent=2) + "\n")
            print(f"  {filename}")

        listing = client.get(f"{BASE}/v1/evaluations?limit=20").raise_for_status().json()

        # One completed evaluation whose findings are clean, and one whose boxes
        # run past 1.0 -- the second is the fixture that proves the models parse a
        # response that violates the contract's own ranges (PHY-69 upstream).
        def out_of_range(ev: dict) -> bool:
            for g in (ev.get("result") or {}).get("glitches") or []:
                for b in ((g.get("region") or {}).get("boxes") or []):
                    if any(not 0 <= v <= 1 for v in b["box"].values()):
                        return True
            return False

        completed = [e for e in listing["data"] if e["status"] == "completed"]
        clean = next((e for e in completed if not out_of_range(e)), None)
        dirty = next((e for e in completed if out_of_range(e)), None)
        for name, ev in [("evaluation_completed.json", clean), ("evaluation_out_of_range.json", dirty)]:
            if ev is None:
                print(f"  ! no candidate for {name}")
                continue
            (OUT / name).write_text(json.dumps(redact_urls(ev), indent=2) + "\n")
            print(f"  {name}  ({ev['id']})")

        (OUT / "evaluation_list.json").write_text(
            json.dumps(redact_urls({"object": "list", "data": [clean] if clean else []}), indent=2) + "\n"
        )
        print("  evaluation_list.json")


if __name__ == "__main__":
    main()
