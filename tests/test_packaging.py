"""What actually ships.

A package can pass its tests and still be broken on install: a missing marker
file so type checkers ignore it, a license the wheel does not carry, models that
enforce ranges the server violates. None of it shows up until somebody installs
it, which is the worst time to find out.
"""

from __future__ import annotations

import inspect
import re
import tomllib
from pathlib import Path

import physionlabs
from physionlabs import models

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_the_package_is_marked_as_typed():
    # Without py.typed, mypy and pyright ignore every annotation in the package
    # and a caller gets `Any` — which is worse than no types, because it looks
    # like types.
    assert (ROOT / "src" / "physionlabs" / "py.typed").exists()


def test_the_license_travels_with_the_distribution():
    # Apache-2.0 section 4 requires the NOTICE to accompany any distribution.
    project = PYPROJECT["project"]
    assert project["license"] == "Apache-2.0"
    assert set(project["license-files"]) == {"LICENSE", "NOTICE"}
    assert (ROOT / "LICENSE").exists()
    assert (ROOT / "NOTICE").exists()


def test_the_runtime_depends_on_two_things_and_no_more():
    # Every dependency is something a consumer has to resolve against their own
    # pins. Two is a client; ten is a framework.
    deps = PYPROJECT["project"]["dependencies"]
    names = sorted(d.split(">")[0].split("=")[0].strip() for d in deps)
    assert names == ["httpx", "pydantic"]


def test_the_models_do_not_enforce_the_contracts_value_ranges():
    # The guard on scripts/generate_models.py. If a regeneration ever emits
    # constraints again, every clip whose findings touch the bottom of the frame
    # becomes unreadable through this SDK — see test_models.py.
    # Matching an annotation, not a substring. The first version of this test
    # searched the whole file and matched the word "constraints" in the generated
    # header comment — a check that fires on prose is one people learn to route
    # around.
    source = inspect.getsource(models)
    annotations = re.findall(r"^\s+\w+:\s*(.+)$", source, re.M)
    for forbidden in ("confloat", "conint", "constr", "EmailStr", "AnyUrl"):
        offenders = [a for a in annotations if forbidden in a]
        assert not offenders, (
            f"models.py annotates with {forbidden} ({offenders[:2]}): value "
            "constraints are back, and a response that violates the contract "
            "will now raise instead of parse"
        )


def test_the_models_are_generated_and_say_so():
    header = (ROOT / "src" / "physionlabs" / "models.py").read_text(encoding="utf8")[:400]
    assert "GENERATED FROM openapi/galileo-v1.yaml" in header
    assert "DO NOT EDIT" in header


def test_the_public_surface_is_explicit():
    # `__all__` is what a caller may rely on. Anything reachable but unlisted is
    # an accident waiting to become a support burden.
    assert "Galileo" in physionlabs.__all__
    assert physionlabs.__version__ == PYPROJECT["project"]["version"]
    for name in physionlabs.__all__:
        assert hasattr(physionlabs, name), f"__all__ names {name}, which does not exist"
