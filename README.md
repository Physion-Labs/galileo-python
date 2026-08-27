# physionlabs

Official Python client for the Galileo video evaluation API.

> **Not published yet.** This repository is under construction; the package does
> not exist on PyPI and the API surface below is not final.

## What Galileo does

Submit a generated video and a prompt; get back the places where the video has
visual defects and the places where it does not do what the prompt asked.

```python
from physionlabs import Galileo

galileo = Galileo()  # reads GALILEO_API_KEY

evaluation = galileo.evaluations.create_and_wait(
    prompt="A red ball rolls off a table and bounces twice.",
    video={"url": "https://cdn.example.com/red-ball.mp4"},
)

# `result` is None on a failed run, so it is worth branching rather than
# reaching straight in — a failed evaluation is an outcome, not an exception.
if evaluation.status.value == "failed":
    print("failed:", evaluation.error.message if evaluation.error else "no reason given")
else:
    for finding in (evaluation.result.glitches if evaluation.result else []):
        print(finding.type.value, finding.description)
```

`partial` is also terminal and DOES carry a result: one detector finished and
another did not, and `detectors` says which of them to trust. A caller waiting
for `completed` alone waits forever.

Uploading a local file instead of pointing at a URL — three calls behind one,
and the bytes are streamed rather than held in memory:

```python
video = galileo.videos.upload("./clip.mp4")
evaluation = galileo.evaluations.create_and_wait(
    prompt="A red ball rolls off a table and bounces twice.",
    video={"upload_id": video.id},
)
```

Walking a large account, and retrying what failed:

```python
for ev in galileo.evaluations.iterate(status=["failed"]):
    nxt = galileo.evaluations.retry(ev.id)   # idempotent, unlike create
    print(ev.id, "->", nxt.id)
```

`retry()` is the only idempotent submission in this API: press it in a burst and
every caller is handed the same successor. `create()` is not, which is why this
client never retries it — see the note in `resources/evaluations.py`.

## The contract

This client is not hand-written against a running server. `openapi/galileo-v1.yaml`
is a copy of the API's OpenAPI description, and the models in
`physionlabs/models.py` are generated from it — so a field cannot be wrong here
without being wrong in the contract.

`openapi/SOURCE` records which upstream revision the copy is.
`python scripts/check_contract.py` fails if the copy has been edited locally, or
if the generated models are not what the contract produces.

The Node client, [`@physionlabs/galileo`](https://github.com/Physion-Labs/galileo-node),
is built from the same copy of the same file.

## Development

```bash
uv sync
uv run python scripts/generate_models.py   # regenerate models from the contract
uv run python scripts/check_contract.py    # verify the copy and the models are in step
uv run pytest
uv run mypy
```

## License

[Apache-2.0](LICENSE). Chosen over MIT for the explicit patent grant: MIT is
silent on patents, which is one more thing for a reviewer to think about, and
Apache-2.0's retaliation clause protects everyone using it.
