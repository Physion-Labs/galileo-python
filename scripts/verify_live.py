"""Does the running service actually answer the way the contract says?

The premise of a frozen contract is that two SDKs can be built against it without
either drifting from the server. Nothing in that premise holds unless something
checks the contract against a real response -- otherwise the document is a
description of what somebody once believed.

So this is not a test of the client. It is a test of the CONTRACT, using the
client to make the calls. And it is the right place for the value ranges the
generated models deliberately do not enforce (see ``generate_models.py``): here a
violation is a report, and everyone can see it. In the models it would be an
exception, and every caller would be broken by our own bug.

    GALILEO_API_KEY=gk_... uv run python scripts/verify_live.py
    GALILEO_BASE_URL=https://api.physionlabs.ai ...   (defaults to the dev deployment)

OpenAPI 3.1 schemas ARE JSON Schema 2020-12, so no translation step is needed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parent.parent
DOC = yaml.safe_load((ROOT / "openapi" / "galileo-v1.yaml").read_text())

BASE_URL = os.environ.get("GALILEO_BASE_URL", "https://api-dev.physionlabs.ai").rstrip("/")
API_KEY = os.environ.get("GALILEO_API_KEY")

# Registered whole, so `$ref: "#/components/schemas/X"` resolves the same way it
# does inside the document. Compiling each schema in isolation would break every
# cross-reference, which is most of them.
# The OpenAPI document declares no `$schema`, so the dialect has to be named
# rather than detected. OpenAPI 3.1 schemas are 2020-12.
_REGISTRY = Registry().with_resource(
    "contract", Resource.from_contents(DOC, default_specification=DRAFT202012)
)


def validate(schema_name: str, value: object) -> list[str]:
    """Validate, and report ROOT CAUSES rather than every consequence.

    A nullable ``$ref`` is a two-branch ``anyOf``, so one bad field inside the
    object branch reports both the real error and "is not of type 'null'" from the
    branch that was never going to match. Dropping a composition error when a more
    specific error exists beneath its path keeps the output readable -- a check
    that buries its finding in its own cascade stops being read.
    """
    validator = Draft202012Validator(
        {"$ref": f"contract#/components/schemas/{schema_name}"}, registry=_REGISTRY
    )

    def flatten(err: object, out: list[tuple[str, str, str]]) -> None:
        """Descend into `context`, where the real error lives.

        `iter_errors` reports a failing `anyOf` as ONE error whose message is the
        whole instance -- the branch errors are in `.context`. Without this the
        output is a dump of the object rather than a statement of what is wrong
        with it, which is what the first version of this function produced.
        """
        path = "/" + "/".join(str(p) for p in err.absolute_path)  # type: ignore[attr-defined]
        out.append((path, err.validator, err.message))  # type: ignore[attr-defined]
        for sub in err.context or []:  # type: ignore[attr-defined]
            flatten(sub, out)

    raw: list[tuple[str, str, str]] = []
    for err in validator.iter_errors(value):
        flatten(err, raw)

    paths = [p for p, _, _ in raw]

    def deeper(p: str) -> bool:
        return any(other != p and other.startswith(p) for other in paths)

    seen: set[str] = set()
    out = []
    for path, keyword, message in raw:
        if keyword in {"anyOf", "oneOf"} and deeper(path):
            continue
        if "is not of type 'null'" in message:
            continue
        line = f"{path or '/'} {message.splitlines()[0][:140]}"
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def get(client: httpx.Client, path: str, *, auth: bool = True) -> object:
    headers = {"authorization": f"Bearer {API_KEY}"} if auth else {}
    response = client.get(f"{BASE_URL}{path}", headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


CASES = [
    ("/v1/status", "SystemStatus", False),
    ("/v1/me", "Account", True),
    ("/v1/models", "ModelList", True),
    ("/v1/quota", "QuotaReport", True),
    ("/v1/credits", "Credits", True),
    ("/v1/evaluations?limit=5", "EvaluationList", True),
]


def main() -> int:
    print(f"Contract: openapi/galileo-v1.yaml\nAgainst:  {BASE_URL}\n")
    failures = 0
    skipped = 0
    with httpx.Client() as client:
        for path, schema, auth in CASES:
            if auth and not API_KEY:
                print(f"  ~ {path}  SKIPPED (no GALILEO_API_KEY)")
                skipped += 1
                continue
            try:
                body = get(client, path, auth=auth)
            except Exception as exc:
                print(f"  ✗ {path}  {exc}")
                failures += 1
                continue
            errors = validate(schema, body)
            if errors:
                failures += 1
                print(f"  ✗ {path}  ({schema})")
                for line in errors[:12]:
                    print(f"      {line}")
                if len(errors) > 12:
                    print(f"      … and {len(errors) - 12} more")
            else:
                print(f"  ✓ {path}  ({schema})")

        # The list carries whole evaluations, so it is also the cheapest way to
        # validate `Evaluation` -- including a completed one, which is the half of
        # the schema worth checking.
        if API_KEY:
            try:
                listing = get(client, "/v1/evaluations?limit=20")
                assert isinstance(listing, dict)
                settled = [
                    e for e in listing["data"] if e["status"] in {"completed", "partial", "failed"}
                ]
                print(f"\n  {len(listing['data'])} evaluation(s), {len(settled)} settled")
                for ev in settled[:5]:
                    errors = validate("Evaluation", ev)
                    if errors:
                        failures += 1
                        print(f"  ✗ evaluation {ev['id']} ({ev['status']})")
                        for line in errors[:8]:
                            print(f"      {line}")
                    else:
                        print(f"  ✓ evaluation {ev['id']} ({ev['status']})")
            except Exception as exc:
                print(f"  ! could not sample evaluations: {exc}")

    # A check that says "verified" when it verified almost nothing is worse than
    # no check: it turns an unverified contract into a green tick. Only one of
    # these cases needs no credential, so without a key this has looked at the
    # simplest endpoint in the API and nothing else.
    if failures:
        print(f"\n{failures} mismatch(es).")
        return 1
    if skipped:
        print(
            f"\nINCOMPLETE — {len(CASES) - skipped} of {len(CASES)} endpoints checked, "
            f"{skipped} skipped for want of GALILEO_API_KEY.\n"
            "The endpoints carrying the interesting half of the contract "
            "(evaluations, models, quota) were NOT verified."
        )
        return 2
    print("\nThe contract matches the live service.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
