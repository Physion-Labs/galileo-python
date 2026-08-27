"""Is this SDK still describing the contract it claims to?

Two failures are possible and only one of them is obvious.

The obvious one: the committed models drift from the contract. Someone edits
``models.py`` by hand, or the contract is synced and the models are not, and from
then on the SDK's public surface is a claim nothing backs. Caught by regenerating
and comparing.

The quiet one: the CONTRACT is edited here. This repo holds a copy of a file
authored upstream, and a copy is only useful while it is a copy -- a change made
here would make this SDK correct against a contract the running service has never
heard of, which is worse than being out of date, because being out of date is
visible. Caught by hashing against ``openapi/SOURCE``.

``openapi/SOURCE`` is provenance, not a signature: someone can edit the yaml and
update the hash. That is fine and deliberate -- the point is that doing so is an
explicit act that shows up in a diff, rather than something a stray editor save
can accomplish.

    uv run python scripts/check_contract.py
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "openapi" / "galileo-v1.yaml"
SOURCE = ROOT / "openapi" / "SOURCE"
MODELS = ROOT / "src" / "physionlabs" / "models.py"


def main() -> int:
    problems: list[str] = []

    # --- 1. the copy is still the copy ------------------------------------
    recorded = re.search(r"^sha256\s*=\s*([0-9a-f]{64})$", SOURCE.read_text(), re.M)
    actual = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    if not recorded:
        problems.append("openapi/SOURCE records no sha256 line.")
    elif recorded.group(1) != actual:
        problems.append(
            "openapi/galileo-v1.yaml does not match the revision openapi/SOURCE names.\n"
            f"  recorded {recorded.group(1)}\n  actual   {actual}\n"
            "If you synced a new contract from upstream, update SOURCE (commit AND sha256).\n"
            "If you edited the contract here, don't: change it upstream and sync."
        )

    # --- 2. the models are still generated from it ------------------------
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "models.py"
        shutil.copy(MODELS, backup)
        before = MODELS.read_text()
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_models.py")],
            capture_output=True,
            text=True,
        )
        after = MODELS.read_text()
        if result.returncode != 0:
            shutil.copy(backup, MODELS)
            problems.append(f"could not regenerate the models:\n{result.stdout}{result.stderr}")
        elif before != after:
            shutil.copy(backup, MODELS)
            problems.append(
                "src/physionlabs/models.py is not what the contract generates.\n"
                "  Run `uv run python scripts/generate_models.py` and commit the result."
            )

    if problems:
        sys.stderr.write("\n" + "\n\n".join(problems) + "\n")
        return 1
    print("Contract copy and generated models are in step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
