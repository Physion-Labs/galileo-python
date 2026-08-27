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

for finding in evaluation.result.glitches:
    print(finding.type, finding.description)
```

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
