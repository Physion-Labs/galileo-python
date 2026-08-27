"""The fields the contract gained at b1e615b, and the ones that became nullable.

Python trailed the contract by three commits; these are what it was missing. Each
is asserted rather than assumed because the models are GENERATED — a field that
silently fails to appear looks exactly like a field nobody asked for.
"""

from __future__ import annotations

from physionlabs.models import Evaluation, EvaluationCounts, EvaluationList, Model, ModelList

from .conftest import fixture


def test_which_attempt_this_is_survives_and_the_lineage_does_not():
    """`attempt` is public; `retry_of` and `retried_by` are not, any more.

    They were, and this test asserted all three. The pair points between ATTEMPT
    ids -- storage keys for rows a caller cannot fetch and has no use for -- and
    `retried_by` exists because the server implements retry idempotency on it.
    That is our mechanism, not a caller's fact, and publishing it would make it
    something we have to keep.

    What a caller actually needs from a retry is which try they are looking at,
    so that is what stays. `POST /v1/evaluations/{id}/retry` answers with the
    successor, which is the link the pair used to provide.
    """
    assert "attempt" in Evaluation.model_fields
    assert not Evaluation.model_fields["attempt"].is_required()

    for gone in ("retry_of", "retried_by", "attempt_id", "superseded_attempts"):
        assert gone not in Evaluation.model_fields, f"{gone} is back on the public model"


def test_an_evaluation_that_still_carries_the_old_lineage_parses_and_drops_it():
    # A response from a task that predates the change, or from the console's own
    # projection. It must not raise -- a client that refuses to parse a response
    # carrying MORE than it expected turns a server change into an outage.
    ev = Evaluation.model_validate(
        {
            **fixture("evaluation_completed"),
            "attempt": 2,
            "retry_of": "01a0456d-4129-770f-b0a5-b49bdcc1ec66",
            "retried_by": None,
        }
    )
    assert ev.attempt == 2
    assert not hasattr(ev, "retry_of")


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
    """The set of statuses is the server's to grow, and growing it must not raise.

    What changed is where the unknown one ENDS UP. It used to be reachable
    through `model_extra`; response models now ignore what the contract does not
    name, so it is dropped. That is the trade this SDK makes on purpose: a field
    in `model_extra` is a field a caller can build on and be broken by, and the
    fix for wanting a new status is a released client that models it.

    The part that matters either way is that parsing succeeds and the statuses
    this client does know are right.
    """
    counts = EvaluationCounts.model_validate({"completed": 3, "quarantined": 1})
    assert counts.completed == 3
    assert not hasattr(counts, "quarantined")


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


def test_an_optional_field_reads_as_absent_rather_than_as_a_value():
    """In Python, absence and null are the same read, and that is the right one.

    This test used to claim the two were distinguished. They are not, and cannot
    be in a generated pydantic model: an optional field becomes `X | None = None`,
    so a key that was absent and a key that was null both come back as `None`.

    That is fine here because the server sends neither for these fields, and it
    is what a caller wants anyway -- `if finding.severity is None` is the correct
    test whichever way the wire spelled it. The contract carries the distinction
    for the readers who need it (it says which fields are sent as an explicit
    null); the client collapses it deliberately.
    """
    from physionlabs.models import PromptMisalignment

    severity = PromptMisalignment.model_fields["severity"]
    assert not severity.is_required()
    assert severity.default is None

    attempt = Evaluation.model_fields["attempt"]
    assert not attempt.is_required()
    assert attempt.default is None

    # optional, and the contract gives it no null: `attempt` is either a number
    # or not there.
    attempt = Evaluation.model_fields["attempt"]
    assert not attempt.is_required()


def test_the_captured_models_response_has_a_null_version():
    # Guards the reason the field is nullable, not just the fact. If a future
    # capture has a version, the nullability is still right but this test should
    # be read again rather than deleted.
    assert fixture("models")["data"][0]["version"] is None
