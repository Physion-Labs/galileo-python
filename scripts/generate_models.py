"""Generate the response models from the contract.

WHY THIS IS NOT JUST A CALL TO THE GENERATOR
--------------------------------------------
Run `datamodel-codegen` on the contract as-is and it faithfully turns every
documented constraint into runtime enforcement: `confloat(ge=0, le=1)` for a
normalized coordinate, `EmailStr` for a field with `format: email`. Both are
correct readings of the document and both are wrong for a client.

A client must not enforce the server's constraints on the server's own output.
A response that violates the contract is the server's bug, and a client that
refuses to parse it turns one bug into a total outage for every caller while
hiding the actual defect. This is not hypothetical: 3.9% of bounding boxes
currently come back with `ymax` a fraction above 1.0 (PHY-69 upstream). Strict
models would have made every clip that touches the bottom of the frame
unreadable through this SDK, and the error would have pointed at the caller.

`format: email` is the same mistake in a smaller way: it would add a mandatory
dependency to every install so that reading a string can fail.

So the constraints are stripped from the schema BEFORE generation rather than
patched out of the generated code afterwards — the transform is then something
you can read and reason about, not a regex over machine output.

WHAT IS KEPT
------------
Structure. Which fields exist, which are required, what type each one is, and
which may be null. That is the contract's actual promise and a caller wants to
know when it is broken. Value ranges are documentation, and belong in
`scripts/verify_live.py`, where a violation is a report rather than an exception.

    uv run python scripts/generate_models.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "openapi" / "galileo-v1.yaml"
OUT = ROOT / "src" / "physionlabs" / "models.py"

# Value constraints: documentation about what the server should send, not
# something a client should refuse to receive.
CONSTRAINTS = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        # `format` earns its place here for the same reason: `email` pulls in a
        # dependency, `uri` changes the Python type from `str` to a URL object,
        # and neither buys a caller anything when reading a response.
        "format",
        # `default` is stripped in BOTH directions, and each has its own reason.
        #
        # On a response it is actively misleading. The contract used to declare
        # `Glitch.source` with `default: model`, which every generator reads as
        # "the server always sends this" — and the server omits it instead. That
        # was a real bug in the contract, found by generating from it.
        #
        # On a request, a client that pre-fills the server's default freezes
        # today's default into every call it ever makes. Omitting the field lets
        # the server apply its own, which is what a default is for.
        "default",
    }
)


def strip(node: object) -> object:
    """Remove value constraints, everywhere, at any depth."""
    if isinstance(node, dict):
        return {k: strip(v) for k, v in node.items() if k not in CONSTRAINTS}
    if isinstance(node, list):
        return [strip(v) for v in node]
    return node


def main() -> int:
    doc = yaml.safe_load(CONTRACT.read_text())
    stripped = strip(doc)

    scratch = ROOT / "openapi" / ".generated-from.yaml"
    scratch.write_text(yaml.safe_dump(stripped, sort_keys=False, allow_unicode=True))
    try:
        result = subprocess.run(
            [
                "datamodel-codegen",
                "--input", str(scratch),
                "--input-file-type", "openapi",
                "--output", str(OUT),
                "--output-model-type", "pydantic_v2.BaseModel",
                "--target-python-version", "3.10",
                "--use-standard-collections",
                "--use-union-operator",
                "--use-schema-description",
                "--use-field-description",
                # Undocumented wire fields (`glitch_category`, `module_versions`)
                # are kept rather than silently dropped: the contract declines to
                # promise them, which is not the same as pretending they are not
                # there. A caller who needs one can reach it.
                "--extra-fields", "allow",
                "--formatters", "black",
                "--disable-timestamp",
                "--custom-file-header",
                "# GENERATED FROM openapi/galileo-v1.yaml -- DO NOT EDIT.\n"
                "# Regenerate with `uv run python scripts/generate_models.py`.\n"
                "# Value constraints are stripped on purpose; see that script.",
            ],
            capture_output=True,
            text=True,
        )
    finally:
        scratch.unlink(missing_ok=True)

    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        return result.returncode
    print(f"{OUT.relative_to(ROOT)}: {len(OUT.read_text().splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
