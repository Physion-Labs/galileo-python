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


ALIAS = '\n\n# ---------------------------------------------------------------------------\n# Appended by scripts/generate_models.py -- see _append_glitch_alias there.\n# ---------------------------------------------------------------------------\n\nGlitch = VisualGlitch | PromptMisalignment\n"""One finding: a visual glitch, or a prompt misalignment.\n\nA union, not a class. Which fields a finding carries depends on its `type`, so\nnarrow on that and the rest follows:\n\n    if finding.type is GlitchType.prompt_misalignment:\n        finding.severity\n    else:\n        finding.region\n"""\n'


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
                # A `oneOf` becomes a RootModel wrapper by default, which would
                # make the SDK's most-read field `finding.root.type` instead of
                # `finding.type`. Collapsing it puts the union at the use site,
                # so a finding IS the narrowed model — the same thing the
                # TypeScript client gets from the same schema.
                "--collapse-root-models",
                # IGNORE, not allow. This used to be `allow`, on the reasoning
                # that the contract declining to promise a field is not the same
                # as pretending it is absent — a caller who needed
                # `glitch_category` or `module_versions` could reach it through
                # `model_extra`.
                #
                # That reasoning was answered upstream rather than argued with:
                # the API now assembles a public response from an allowlist, so
                # those fields are not sent to an API key at all and there is
                # nothing for `allow` to preserve. What it does preserve is a
                # promise we cannot keep — that whatever the server happens to
                # send is reachable and therefore usable. `model_extra` is where
                # a caller would find a field we never documented, build on it,
                # and be broken by a release that stops sending it.
                #
                # `ignore` also makes a leak visible from the client side: an
                # internal field reaching a response ends up nowhere rather than
                # quietly in `model_extra`, and the test that asserts
                # `model_extra` is empty is then a real check on the service.
                "--extra-fields", "ignore",
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
    _append_glitch_alias()
    print(f"{OUT.relative_to(ROOT)}: {len(OUT.read_text().splitlines())} lines")
    return 0


def _append_glitch_alias() -> None:
    """Give the union back its name.

    `--collapse-root-models` puts the union at the use site, which is what makes
    a finding `finding.type` instead of `finding.root.type`. The cost is that the
    generator then emits no `Glitch` symbol at all -- and `Glitch` is a name this
    package has already published, and the name the TypeScript client uses for
    the same schema.

    Appended by the generator rather than written into the file by hand: the file
    says DO NOT EDIT and means it, so the one thing added to it is added by the
    thing that owns it.
    """
    OUT.write_text(OUT.read_text() + ALIAS)



if __name__ == "__main__":
    raise SystemExit(main())
