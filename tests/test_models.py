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


def test_a_finding_carries_only_the_fields_its_kind_has():
    """This test used to assert the opposite, and the opposite used to be true.

    The service sent `severity: null` on every visual glitch, and
    `prompt_segment: null` beside it, so the contract said the keys were present
    with null values and these models agreed.

    The response is now assembled per finding type, so a visual glitch has no
    `severity` at all -- not null, absent -- and the models are a union narrowed
    on `type`. Reaching for `severity` on a visual glitch is now a type error
    rather than a None, which is the improvement: the old shape let you write it
    and never told you it could not be a number.
    """
    from physionlabs.models import PromptMisalignment, VisualGlitch

    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.result is not None

    vg = [g for g in evaluation.result.glitches if isinstance(g, VisualGlitch)]
    assert vg, "the fixture should contain a visual glitch"
    assert not hasattr(vg[0], "severity")
    assert not hasattr(vg[0], "prompt_segment")
    assert vg[0].region is not None

    pm = [g for g in evaluation.result.glitches if isinstance(g, PromptMisalignment)]
    assert pm, "the fixture should contain a prompt misalignment"
    assert not hasattr(pm[0], "region")
    assert pm[0].prompt_segment is not None


def test_metadata_is_null_when_the_caller_passed_none():
    # Found by making a real request rather than by reading the code: every
    # evaluation created in the console carries metadata, so the contract looked
    # right against all existing traffic and was wrong for the first request an
    # SDK ever made.
    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.metadata is None


def test_a_field_outside_the_contract_ends_up_nowhere():
    """Undocumented fields are DROPPED, not parked in `model_extra`.

    This test used to assert the opposite, on the reasoning that the contract
    declining to promise `glitch_category` was not the same as pretending it was
    absent — so `extra="allow"` kept it reachable.

    The reasoning was answered upstream rather than argued with: the API now
    assembles an API-key response from an allowlist, so those fields are not sent
    at all and there is nothing for `allow` to preserve. What `allow` did preserve
    was a promise we cannot keep — that whatever the server happens to send is
    reachable, and therefore something a caller can build on and be broken by.

    The fixture is a REAL response captured before that change, plus fields no
    release has produced. Both are ignored the same way, which is the point: the
    default for an unknown field is to disappear, not to become an attribute.
    """
    evaluation = Evaluation.model_validate(fixture("evaluation_with_internal_fields"))
    assert evaluation.model_extra == {} or evaluation.model_extra is None

    assert evaluation.result is not None
    for finding in evaluation.result.glitches:
        assert finding.model_extra == {} or finding.model_extra is None

    # Named individually as well, because an empty `model_extra` would also be
    # what a parse that silently failed produced.
    for internal in (
        "module_versions",
        "owner_id",
        "internal_versions",
        "timings",
        "future_internal_field",
    ):
        assert not hasattr(evaluation, internal), f"{internal} became an attribute"

    # And the thing the caller DID come for survived all of that.
    assert evaluation.status.value == "completed"
    assert evaluation.result.summary.num_glitches == len(evaluation.result.glitches)


def test_a_run_says_how_long_it_took():
    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.timing is not None
    assert evaluation.timing.e2e_ms == 43000
    # One number, so a caller cannot reach for the model server's clock by mistake.
    assert set(evaluation.timing.model_dump().keys()) == {"e2e_ms"}


def test_an_unmeasured_run_reads_as_unmeasured_and_not_as_instant():
    body = fixture("evaluation_completed")
    body["timing"] = None
    assert Evaluation.model_validate(body).timing is None

    # Absent, not null: a response from a task that predates the field.
    del body["timing"]
    assert Evaluation.model_validate(body).timing is None


def test_severity_means_what_the_contract_says():
    # `6 - score`, so 5 is a requirement the video ignored entirely. The captured
    # evaluation was submitted with a prompt that deliberately did not match the
    # video, and both prompt findings came back at 5.
    evaluation = Evaluation.model_validate(fixture("evaluation_completed"))
    assert evaluation.result is not None
    # `type` is a plain string here, not the GlitchType enum: pydantic needs a
    # Literal to discriminate the union on. `isinstance` reads better and is what
    # the test above uses; this one compares the string to show both work.
    pm = [g for g in evaluation.result.glitches if g.type == "prompt_misalignment"]
    assert pm, "the fixture should contain prompt misalignments"
    for finding in pm:
        assert finding.severity is not None
        assert 1 <= finding.severity <= 5
