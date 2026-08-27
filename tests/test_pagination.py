"""Paging and the census, which is the part easy to get subtly wrong.

`counts` is a per-status census over the same owner and video scope as the
request, and it IGNORES `status` — the contract says so. Summing all of it while
filtering walks past the end of the filtered set.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from .conftest import Recorder, fixture, ok


def _evaluation(eid: str) -> dict:
    """A real evaluation with a chosen id.

    Built from the captured response rather than written out, because the Python
    models validate at RUNTIME — a hand-made dict missing a required field fails
    in the model rather than in the code under test. (The Node client's types are
    compile-time only, which is why the same test there can use three fields.
    That difference is worth knowing when porting a test between the two.)
    """
    return {**fixture("evaluation_completed"), "id": eid}


def _page(ids: list[str], counts: dict[str, int]) -> dict:
    return {"object": "list", "data": [_evaluation(i) for i in ids], "counts": counts}


def _query(url: object) -> dict[str, list[str]]:
    return parse_qs(urlparse(str(url)).query)


def test_list_sends_offset_and_comma_joins_status(client_factory):
    rec = Recorder(ok(_page([], {})))
    client_factory(rec).evaluations.list(limit=5, offset=40, status=["failed", "partial"])
    q = _query(rec.calls[0].url)
    assert q["offset"] == ["40"]
    assert q["status"] == ["failed,partial"]


def test_an_empty_status_list_is_omitted_rather_than_sent_empty(client_factory):
    # `?status=` asks the server to keep nothing, which is the opposite of "no
    # filter" — and a caller building the list from checkboxes hits this.
    rec = Recorder(ok(_page([], {})))
    client_factory(rec).evaluations.list(status=[])
    assert "status" not in _query(rec.calls[0].url)


def test_iterate_pages_on_counts_not_on_a_short_page(client_factory):
    # Three of five, then two. Page one is FULL and is not the end, which is
    # precisely what a short-page test cannot tell.
    rec = Recorder(
        ok(_page(["a", "b", "c"], {"completed": 5})),
        ok(_page(["d", "e"], {"completed": 5})),
    )
    seen = [e.id for e in client_factory(rec).evaluations.iterate(page_size=3)]
    assert seen == ["a", "b", "c", "d", "e"]
    assert len(rec.calls) == 2, "and it stops at the census without a third request"
    assert _query(rec.calls[1].url)["offset"] == ["3"]


def test_a_filtered_iterate_selects_its_statuses_out_of_the_census(client_factory):
    # 5 completed among 100 failed. Summing the whole census would walk to 105 —
    # 33 more pages, every one of them empty.
    counts = {"queued": 0, "processing": 0, "completed": 5, "partial": 0, "failed": 100}
    rec = Recorder(ok(_page(["a", "b", "c"], counts)), ok(_page(["d", "e"], counts)))
    seen = [e.id for e in client_factory(rec).evaluations.iterate(page_size=3, status=["completed"])]
    assert seen == ["a", "b", "c", "d", "e"]
    assert len(rec.calls) == 2
    for call in rec.calls:
        assert _query(call.url)["status"] == ["completed"]


def test_a_status_the_census_does_not_mention_counts_as_zero(client_factory):
    # A deployment that adds a status this client has not heard of must not break
    # paging for a client that is not asking for it.
    rec = Recorder(ok(_page([], {"completed": 3})))
    assert list(client_factory(rec).evaluations.iterate(status=["cancelled"])) == []
    assert len(rec.calls) == 1


def test_iterate_still_terminates_without_a_census(client_factory):
    rec = Recorder(ok({"object": "list", "data": [_evaluation("a")]}))
    assert [e.id for e in client_factory(rec).evaluations.iterate(page_size=3)] == ["a"]
    assert len(rec.calls) == 1
