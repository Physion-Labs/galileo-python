"""The models must parse what the server actually sends.

This is the file that guards the decision in `scripts/generate_models.py`: the
generated models describe the contract's SHAPE but do not enforce its value
ranges. Generate them straight from the document and `datamodel-codegen`
faithfully emits `confloat(ge=0, le=1)` for a normalized coordinate — at which
point 3.9% of real clips become unreadable through this SDK, and the traceback
points at the caller.
"""

from __future__ import annotations

from physionlabs.models import Account, Credits, Evaluation, ModelList, QuotaReport, SystemStatus

from .conftest import fixture


def test_every_captured_response_parses():
    SystemStatus.model_validate(fixture("status"))
    Account.model_validate(fixture("account"))
    ModelList.model_validate(fixture("models"))
    QuotaReport.model_validate(fixture("quota"))
    Credits.model_validate(fixture("credits"))
    Evaluation.model_validate(fixture("evaluation_completed"))


def test_a_response_that_violates_the_contracts_own_ranges_still_parses():
    # `evaluation_out_of_range` is a real response whose boxes run past ymax=1.0
    # (PHY-69 upstream). A client that refused it would turn our bug into an
    # outage for every caller, and hide the defect while doing so.
    raw = fixture("evaluation_out_of_range")
    evaluation = Evaluation.model_validate(raw)
    assert evaluation.result is not None

    over = [
        b.box.ymax
        for g in evaluation.result.glitches
        if g.region
        for b in g.region.boxes
        if b.box.ymax > 1.0
    ]
    assert over, "this fixture is supposed to contain out-of-range boxes"
    assert max(over) > 1.0, "and the model is supposed to hand them over unchanged"


def test_nulls_are_values_not_missing_keys():
    # The service sends `severity: null` rather than omitting the key, on every
    # visual glitch. The contract says so; these models have to agree.
    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.result is not None
    vg = [g for g in evaluation.result.glitches if g.type.value == "visual_glitch"]
    assert vg, "the fixture should contain a visual glitch"
    assert vg[0].severity is None
    assert vg[0].prompt_segment is None


def test_metadata_is_null_when_the_caller_passed_none():
    # Found by making a real request rather than by reading the code: every
    # evaluation created in the console carries metadata, so the contract looked
    # right against all existing traffic and was wrong for the first request an
    # SDK ever made.
    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.metadata is None


def test_undocumented_wire_fields_are_kept_rather_than_dropped():
    # `glitch_category` and `module_versions` are on the wire and deliberately not
    # in the contract. Not promising them is not the same as pretending they are
    # absent, so `extra="allow"` keeps them reachable for anyone who needs one.
    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.result is not None
    extra = evaluation.result.glitches[0].model_extra or {}
    assert "glitch_category" in extra
    assert "module_versions" in (evaluation.model_extra or {})


def test_severity_means_what_the_contract_says():
    # `6 - score`, so 5 is a requirement the video ignored entirely. The captured
    # evaluation was submitted with a prompt that deliberately did not match the
    # video, and both prompt findings came back at 5.
    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.result is not None
    pm = [g for g in evaluation.result.glitches if g.type.value == "prompt_misalignment"]
    assert pm, "the fixture should contain prompt misalignments"
    for finding in pm:
        assert finding.severity is not None
        assert 1 <= finding.severity <= 5
