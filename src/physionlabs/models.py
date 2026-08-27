# GENERATED FROM openapi/galileo-v1.yaml -- DO NOT EDIT.
# Regenerate with `uv run python scripts/generate_models.py`.
# Value constraints are stripped on purpose; see that script.

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, Any, Dict, Literal


class ModelId(Enum):
    galileo = 'galileo'
    gemini = 'gemini'


class GlitchType(Enum):
    visual_glitch = 'visual_glitch'
    prompt_misalignment = 'prompt_misalignment'


class EvaluationStatus(Enum):
    queued = 'queued'
    processing = 'processing'
    completed = 'completed'
    partial = 'partial'
    failed = 'failed'


class DetectorStatus(Enum):
    pending = 'pending'
    reused = 'reused'
    completed = 'completed'
    failed = 'failed'
    skipped = 'skipped'


class VideoStatus(Enum):
    pending = 'pending'
    processing = 'processing'
    ready = 'ready'
    failed = 'failed'


class ContentType(Enum):
    """
    Only MP4 is accepted.
    """

    video_mp4 = 'video/mp4'


class VideoCreate(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    content_type: ContentType
    """
    Only MP4 is accepted.
    """
    size_bytes: int
    """
    Exact size of the file you are about to send. It is signed into the grant, so the storage endpoint refuses a body that exceeds it -- an understated size fails the PUT rather than the reservation.
    """
    content_hash: str | None = None
    """
    SHA-256 of the bytes, hex. Optional, and worth sending: when we already hold this exact content the response says `skip_upload` and there is nothing to transfer.
    """
    duration_sec: float | None = None
    """
    Optional metadata recorded on the video.
    """
    width: int | None = None
    """
    Optional metadata recorded on the video.
    """
    height: int | None = None
    """
    Optional metadata recorded on the video.
    """


class VideoReservation(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    video_id: str
    """
    Reference this as the evaluation's `video.upload_id`, once the video reaches `ready`.
    """
    cdn_url: str
    """
    Where the bytes will be readable once the upload completes.
    """
    upload_path: str | None = None
    """
    Where to PUT the bytes. A path or absolute URL on separate storage infrastructure, valid for 15 minutes, carrying its own signed grant -- send no `Authorization` header with it. Absent when `skip_upload` is true.
    """
    skip_upload: bool | None = None
    """
    Present and true when `content_hash` matched content we already hold. Skip straight to referencing `video_id`: there is nothing to upload and no completion call to make.
    """


class Video(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    id: str
    object: Literal['video'] | None = None
    status: VideoStatus
    cdn_url: str
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    created: int | None = None
    """
    Unix seconds.
    """


class VideoUrlRef(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    url: str
    """
    Public HTTP or HTTPS URL for an MP4 video.
    """


class VideoBase64Ref(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    b64_json: str = Field(..., json_schema_extra={'contentEncoding': 'base64'})
    """
    Base64-encoded MP4 bytes, sent inline with the request.
    Bounded by the 2 MB request body limit, not by the 50 MB file limit: base64 costs a third more than the bytes it carries, so the largest clip that fits inline is roughly 1.5 MB. That is well under a typical 15-second render. Use `url` for anything larger -- a body over the limit is rejected with 413, which is a transport failure rather than a validation one and so is not in this endpoint's error list.
    """


class VideoUploadRef(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    upload_id: str
    """
    The `video_id` of a video you uploaded and whose status has reached `ready`. See `POST /v1/videos`.
    """


class EvaluationCreate(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    model: ModelId | None = None
    model_version: str | None = None
    """
    Concrete model version to run. The deployment default applies when omitted.
    """
    prompt: str
    """
    What the video was meant to show. REQUIRED as of 2026-08-27 (previously optional, defaulting to ""); empty or whitespace-only is refused with `missing_prompt`.
    """
    video: VideoUrlRef | VideoUploadRef | VideoBase64Ref
    """
    How to give us the video. Exactly one of the three, and the choice is mostly about size.
    `upload_id` is the general answer: upload the file first (three calls, one of them straight to storage -- see `POST /v1/videos`) and reference it here. It is the only option that both reaches the 50 MB file limit and keeps the video private to your account.
    `url` is the shortcut when the video is already hosted somewhere we can GET. Note that it has to be publicly reachable; we send no credentials.
    `b64_json` sends the bytes inline. Convenient for a small local file, but bounded by the request body limit rather than the file limit -- see `POST /v1/evaluations`.
    """
    glitch_types: list[GlitchType] | None = None
    metadata: dict[str, Any] | None = None
    """
    JSON metadata echoed on the evaluation. Serialized size must not exceed 8192 bytes.
    """


class TimePoint(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    frame: int
    sec: float
    timecode: str


class BoundingBox(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    xmin: float
    ymin: float
    xmax: float
    ymax: float


class BoxKeyframe(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    frame: int
    sec: float
    box: BoundingBox


class GlitchRegion(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    start: TimePoint
    end: TimePoint
    boxes: list[BoxKeyframe]


class PromptSegment(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    text: str
    char_start: int
    char_end: int


class GlitchSource(Enum):
    """
    Who produced this finding. Absent means the model, which is the common case -- the field is only set explicitly where a human annotated something the model missed, so treat its absence as `model` rather than as unknown.
    Deliberately NOT declared with a `default`. A default reads to a code generator as "the server always sends this", and it does not: the value is omitted, not defaulted, and a generated type that made it required would be wrong on almost every finding.
    """

    model = 'model'
    human = 'human'


class VisualGlitch(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    id: str
    type: Literal['visual_glitch']
    description: str
    source: GlitchSource | None = None
    region: GlitchRegion | None = None
    """
    Where in the video this finding is, with per-frame boxes.
    Absent on a finding the detector localised no further than the clip.
    """


class PromptMisalignment(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    id: str
    type: Literal['prompt_misalignment']
    description: str
    source: GlitchSource | None = None
    prompt_segment: PromptSegment | None = None
    """
    The span of your prompt this finding is about.
    """
    severity: int | None = None
    """
    How far a prompt requirement was from being realized: `6 - score`, so 1 is a minor mismatch and 5 means the requirement is absent entirely. It reads in the OPPOSITE direction from a score, which is the one thing worth getting right before you threshold on it.
    This is also the number our own reporting threshold reads, so a finding you receive is by definition one that cleared it.
    There is deliberately no `confidence` beside it. That is the model's certainty about its own answer -- a different axis, not stable across releases, and not calibrated for anyone outside to threshold on.
    Optional: a finding from an older pipeline may carry no score.
    """


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    num_glitches: int
    has_visual_glitch: bool
    has_prompt_misalignment: bool


class VideoInfo(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    duration_sec: float
    width: int
    height: int
    fps: float
    num_frames: int


class Timing(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    e2e_ms: int
    """
    Milliseconds from submission to the terminal answer, measured by the service. This is what you waited: it includes our queueing, fetching the video, and the model's own time.
    One number rather than a breakdown, deliberately. The finer measurements are the model server's own clock in its own units, and a number read from the wrong level is wrong by three orders of magnitude rather than plausibly close.
    """


class EvaluationUsage(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    video_seconds: float
    billable_units: float


class DetectorError(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    code: str
    message: str


class DetectorState(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    detector: GlitchType
    status: DetectorStatus
    error: DetectorError | None = None


class EvaluationFailure(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    type: str
    code: str
    message: str
    request_id: str


class Input(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    prompt: str
    video: VideoInfo


class EvaluationCounts(BaseModel):
    """
    How many evaluations exist in each status, over the same owner and video scope as the request and deliberately IGNORING `limit`, `offset` and `status`.
    This is what a pager needs. Inferring the end of a list from "was the page full" is wrong at exactly the boundary paging exists to make honest, and a bare total could not tell you the page count for a filtered view.
    """

    model_config = ConfigDict(
        extra='ignore',
    )
    __annotations__ = {
        '__pydantic_extra__': Dict[str, int],
    }
    queued: int | None = None
    processing: int | None = None
    completed: int | None = None
    partial: int | None = None
    failed: int | None = None


class RateLimitWindow(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    limit: int
    used: int
    remaining: int
    reset_at: int | None
    reset_in_sec: int | None
    window_sec: int
    unlimited: bool


class QuotaScopes(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    detect: RateLimitWindow
    generate: RateLimitWindow
    upload: RateLimitWindow


class QuotaReport(RateLimitWindow):
    model_config = ConfigDict(
        extra='ignore',
    )
    scopes: QuotaScopes


class RateLimitDefinition(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    max: int
    window_sec: int


class ApiKeySummary(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    name: str
    prefix: str
    last4: str


class ModelBuild(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    id: ModelId
    label: str
    version: str | None
    """
    The build the model runs, or NULL when that is not ours to state.
    Null is the current answer for `galileo` and will stay so while it is the default: the version belongs to the cluster serving it, and answering from our side would mean publishing a number nobody checked. Nothing keys a run on this -- an evaluation carries its own `model_version`, taken from the submission that resolved it, and that is the one to read.
    """
    note: str | None = None


class Input1(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    formats: list[str]
    max_duration_sec: float
    max_file_bytes: int
    aspect_ratios: list[str]


class Model(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    id: ModelId
    object: Literal['model']
    version: str | None
    """
    The build the model runs, or NULL when that is not ours to state.
    Null is the current answer for `galileo` and will stay so while it is the default: the version belongs to the cluster serving it, and answering from our side would mean publishing a number nobody checked. Nothing keys a run on this -- an evaluation carries its own `model_version`, taken from the submission that resolved it, and that is the one to read.
    """
    detectors: list[GlitchType]
    input: Input1


class ModelList(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    object: Literal['list']
    builds: list[ModelBuild]
    default_build: str | None
    """
    The build an evaluation gets when it names no `model_version`, or NULL when that is the cluster's to state — see `Model.version`. Describes the deployment; it is not what a run is filed under.
    """
    data: list[Model]


class PerSecondByDetector(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    visual_glitch: float | None = None
    prompt_misalignment: float | None = None


class PricingRates(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    per_second_per_detector: float
    per_second_by_detector: PerSecondByDetector | None = None
    cache_hit_rate: float
    assumed_duration_sec: float
    generation_from_catalog: bool | None = None


class Credits(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    credits: float
    pricing: PricingRates
    unlimited: bool
    per_generated_sec: float


class ComponentState(Enum):
    operational = 'operational'
    degraded = 'degraded'
    down = 'down'
    unknown = 'unknown'


class ComponentStatus(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    key: str
    name: str
    description: str
    state: ComponentState
    detail: str
    latency_ms: float | None


class SystemStatus(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    state: ComponentState
    checked_at: int
    components: list[ComponentStatus]


class ErrorType(Enum):
    invalid_request_error = 'invalid_request_error'
    authentication_error = 'authentication_error'
    rate_limit_error = 'rate_limit_error'
    api_error = 'api_error'


class ErrorCode(Enum):
    invalid_body = 'invalid_body'
    unknown_model = 'unknown_model'
    missing_video = 'missing_video'
    missing_prompt = 'missing_prompt'
    prompt_too_long = 'prompt_too_long'
    invalid_glitch_types = 'invalid_glitch_types'
    video_too_long = 'video_too_long'
    invalid_video = 'invalid_video'
    not_found = 'not_found'
    not_implemented = 'not_implemented'
    insufficient_credits = 'insufficient_credits'
    missing_api_key = 'missing_api_key'
    invalid_api_key = 'invalid_api_key'
    unauthenticated = 'unauthenticated'
    rate_limited = 'rate_limited'
    concurrency_limit = 'concurrency_limit'
    internal_error = 'internal_error'
    model_unavailable = 'model_unavailable'
    model_output_invalid = 'model_output_invalid'
    model_timeout = 'model_timeout'
    run_abandoned = 'run_abandoned'


class Error(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    type: ErrorType
    code: ErrorCode
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    error: Error
    quota: RateLimitWindow | None = None


class EvaluationResult(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    glitches: list[
        Annotated[VisualGlitch | PromptMisalignment, Field(discriminator='type')]
    ]
    summary: EvaluationSummary


class Evaluation(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    id: str
    object: Literal['evaluation']
    model: ModelId
    model_version: str
    output_schema_version: str
    created: int
    """
    Unix timestamp in seconds.
    """
    status: EvaluationStatus
    input: Input
    usage: EvaluationUsage
    result: EvaluationResult | None
    error: EvaluationFailure | None = None
    """
    Why the run failed, on a `failed` one. NULL on a run that did not fail, and ABSENT on rows written before this field existed.
    Not in `required`, and that is a correction rather than a preference: it was, and the older rows in the store do not carry the key at all. A client that enforced the contract at runtime — the Python one does, since its models validate — raised on any page deep enough to reach them, while the TypeScript client passed because its types are erased before a response is ever seen. So the contract was not merely wrong, it was wrong in a way that only one of the two clients could report.
    Test for a VALUE, not for the key.
    """
    detectors: list[DetectorState] | None = None
    """
    Per-detector state. Older evaluations may omit this field.
    """
    video_id: str | None = None
    """
    Stored video identifier when the evaluation used an uploaded video.
    """
    attempt: int | None = None
    """
    Which try this is. 1 for a run submitted directly; 2 or more for one produced by `POST /v1/evaluations/{evaluation_id}/retry`. There is a ceiling, so a clip that keeps failing under the same instructions stops being retryable rather than being retried forever.
    """
    timing: Timing | None = None
    """
    How long this run took. NULL when nothing was measured -- which is every run settled before it was recorded, and is not backfillable.
    Null and never 0. A run whose latency nobody recorded and a run that took no time are different claims, and only one of them is true.
    NOT in `required`, for the same reason `error` is not: during a rolling deploy some tasks are still the older build, and a response from one of those carries no such key. A client that enforces the contract at runtime -- the Python one does -- would raise on those responses, and it would raise only during a deploy, which is the worst time to be debugging a client. Test for a VALUE, not for the key.
    """
    metadata: dict[str, Any] | None = None
    """
    Whatever you passed on create, echoed back. NULL when you passed nothing -- the key is always present, its value says whether there was any.
    Only found by submitting through the API. Every evaluation created in the console carries metadata, so a contract checked against console traffic alone looked correct here.
    """


class EvaluationList(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    object: Literal['list']
    data: list[Evaluation]
    counts: EvaluationCounts | None = None


class RateLimits(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    detect: RateLimitDefinition
    generate: RateLimitDefinition
    upload: RateLimitDefinition


class AccountLimits(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    requests_per_min: int
    window_sec: int
    max_concurrent_jobs: int
    rate_limits: RateLimits


class Account(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
    )
    object: Literal['user']
    id: str | None
    email: str | None
    name: str | None
    tier: str
    credits: float
    unlimited: bool
    limits: AccountLimits
    api_key: ApiKeySummary | None = None


# ---------------------------------------------------------------------------
# Appended by scripts/generate_models.py -- see _append_glitch_alias there.
# ---------------------------------------------------------------------------

Glitch = VisualGlitch | PromptMisalignment
"""One finding: a visual glitch, or a prompt misalignment.

A union, not a class. Which fields a finding carries depends on its `type`, so
narrow on that and the rest follows:

    if finding.type is GlitchType.prompt_misalignment:
        finding.severity
    else:
        finding.region
"""
