"""The fields the contract gained at b1e615b, and the ones that became nullable.

Python trailed the contract by three commits; these are what it was missing. Each
is asserted rather than assumed because the models are GENERATED — a field that
silently fails to appear looks exactly like a field nobody asked for.
"""

from __future__ import annotations

from physionlabs.models import Evaluation, EvaluationCounts, EvaluationList, Model, ModelList

from .conftest import fixture


def test_the_retry_trio_is_modelled():
    # Without these a caller who retries cannot link the two runs, and
    # `retried_by` is the field the server's idempotency is implemented on.
    for field in ("attempt", "retry_of", "retried_by"):
        assert field in Evaluation.model_fields, f"Evaluation is missing {field}"
        assert not Evaluation.model_fields[field].is_required(), f"{field} must be optional"


def test_an_evaluation_carrying_the_retry_trio_parses():
    ev = Evaluation.model_validate(
        {**fixture("evaluation_completed"), "attempt": 2, "retry_of": "eval_1", "retried_by": None}
    )
    assert ev.attempt == 2
    assert ev.retry_of == "eval_1"
    assert ev.retried_by is None


def test_the_list_carries_a_census():
    assert "counts" in EvaluationList.model_fields
    page = EvaluationList.model_validate(
        {
            "object": "list",
            "data": [],
            "counts": {"queued": 1, "processing": 0, "completed": 23, "partial": 0, "failed": 2},
        }
    )
    assert page.counts is not None
    assert page.counts.completed == 23


def test_a_census_with_a_status_this_client_has_not_heard_of_still_parses():
    # `EvaluationCounts` allows additional integer properties on purpose: the set
    # of statuses is the server's to grow.
    counts = EvaluationCounts.model_validate({"completed": 3, "quarantined": 1})
    assert counts.completed == 3
    assert (counts.model_extra or {}).get("quarantined") == 1


def test_model_versions_are_nullable():
    # The live service returns null for all three: galileo's version belongs to
    # the cluster serving it, so answering from our side would publish a number
    # nobody checked. Strict models would reject every /v1/models response.
    listing = ModelList.model_validate(fixture("models"))
    assert listing.default_build is None or isinstance(listing.default_build, str)
    for model in listing.data:
        assert model.version is None or isinstance(model.version, str)
    for build in listing.builds:
        assert build.version is None or isinstance(build.version, str)

    # REQUIRED, and NULLABLE. Not the same thing, and the contract means both:
    # `version` is in Model's `required` list, so the key is always sent, and its
    # type is `[string, "null"]`, so the value may be nothing. That is the honest
    # encoding of "the cluster owns this number and we cannot state it" — as
    # opposed to an absent key, which would say "there is no such field".
    #
    # An earlier version of this assertion checked `not is_required()` and failed,
    # having conflated the two. Worth keeping the distinction stated: elsewhere in
    # this contract `severity` and `metadata` are optional AND nullable, and
    # `attempt` is optional and not nullable.
    version = Model.model_fields["version"]
    assert version.is_required(), "the key is always sent"
    assert type(None) in getattr(version.annotation, "__args__", ()), "the value may be null"


def test_optional_and_nullable_are_distinguished():
    from physionlabs.models import Glitch

    # optional and nullable — the key may be absent, and null when present
    severity = Glitch.model_fields["severity"]
    assert not severity.is_required()
    assert type(None) in getattr(severity.annotation, "__args__", ())

    # optional, and the contract gives it no null: `attempt` is either a number
    # or not there.
    attempt = Evaluation.model_fields["attempt"]
    assert not attempt.is_required()


def test_the_captured_models_response_has_a_null_version():
    # Guards the reason the field is nullable, not just the fact. If a future
    # capture has a version, the nullability is still right but this test should
    # be read again rather than deleted.
    assert fixture("models")["data"][0]["version"] is None
