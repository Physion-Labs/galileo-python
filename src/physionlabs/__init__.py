"""physionlabs -- official Python client for the Galileo video evaluation API.

    from physionlabs import Galileo

    galileo = Galileo()
    evaluation = galileo.evaluations.create_and_wait(
        prompt="A red ball rolls off a table and bounces twice.",
        video={"url": "https://cdn.example.com/red-ball.mp4"},
    )

The response models in `physionlabs.models` are GENERATED from the API's OpenAPI
description (`openapi/galileo-v1.yaml`), so a field cannot be wrong here without
being wrong in the contract. They do not enforce the contract's value ranges --
see `scripts/generate_models.py` for why a client must not refuse to parse its
own server's output.
"""

from __future__ import annotations

from ._client import DEFAULT_BASE_URL, Galileo
from .errors import (
    APIError,
    AuthenticationError,
    ConnectionError,
    GalileoError,
    InsufficientCreditsError,
    InvalidRequestError,
    NotFoundError,
    PollTimeoutError,
    RateLimitError,
    ServerError,
)
from .models import (
    Account,
    BoundingBox,
    BoxKeyframe,
    Credits,
    Evaluation,
    EvaluationList,
    EvaluationResult,
    EvaluationSummary,
    Glitch,
    GlitchRegion,
    GlitchType,
    Model,
    ModelList,
    PromptSegment,
    QuotaReport,
    SystemStatus,
    TimePoint,
    Video,
    VideoStatus,
)

__version__ = "0.1.0rc3"

__all__ = [
    "Galileo",
    "DEFAULT_BASE_URL",
    "__version__",
    # errors
    "GalileoError",
    "APIError",
    "InvalidRequestError",
    "AuthenticationError",
    "NotFoundError",
    "InsufficientCreditsError",
    "RateLimitError",
    "ServerError",
    "ConnectionError",
    "PollTimeoutError",
    # models
    "Account",
    "BoundingBox",
    "BoxKeyframe",
    "Credits",
    "Evaluation",
    "EvaluationList",
    "EvaluationResult",
    "EvaluationSummary",
    "Glitch",
    "GlitchRegion",
    "GlitchType",
    "Model",
    "ModelList",
    "PromptSegment",
    "QuotaReport",
    "SystemStatus",
    "TimePoint",
    "Video",
    "VideoStatus",
]
