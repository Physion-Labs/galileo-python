# physionlabs

Official Python client for the Galileo video evaluation API.

> **Release candidate.** `pip install physionlabs` resolves it. The API below is
> not final until 0.1.0, and this notice is what will change when it is.

## Setup

```bash
pip install --pre physionlabs
export GALILEO_API_KEY="your-api-key"
```

The new `Client` API requires rc.6 or newer. Put an H.264 MP4 named `video.mp4`
in the working directory (at most 15 seconds and 50 MiB), and replace the prompt
below with what your video was meant to show.

## What Galileo does

Submit a generated video and a prompt; get back the places where the video has
visual defects and the places where it does not do what the prompt asked.

```python
from physionlabs import Client

client = Client()  # reads GALILEO_API_KEY

evaluation = client.evaluations.create(
    model="galileo-1.0",
    input={
        "video": {"path": "./video.mp4"},
        "prompt": "A red ball rolls off a table and bounces twice.",
    },
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

Uploading separately to reuse a video across evaluations:

```python
video = client.videos.upload("./clip.mp4")
if video.status.value != "ready":
    raise ValueError("Video failed validation.")
evaluation = client.evaluations.create(
    model="galileo-1.0",
    input={
        "video": {"upload_id": video.id},
        "prompt": "A red ball rolls off a table and bounces twice.",
    },
)
```

Walking a large account, and retrying what failed:

```python
for ev in client.evaluations.iterate(status=["failed"]):
    nxt = client.evaluations.retry(ev.id)   # idempotent, unlike create
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


## Submit without waiting

`Client.evaluations.create()` handles upload, validation, submission and waiting
for the result. `Client.evaluations.submit()` accepts the same `model` and `input`
but returns the job ID after submission. A local file still has to finish
uploading and validating first. Use `retrieve(id)` to read the result later.
For a hosted video, use `input.video.url` instead of `input.video.path`.

## Migrating from rc.5

Import `Client`, move `video` and `prompt` into `input`, and select
`galileo-1.0`. Replace create-and-wait with `create`, and submit-only `create`
with `submit`. The original `Galileo` entry point retains its old behavior.
