# GENERATED FROM openapi/galileo-v1.yaml -- DO NOT EDIT.
# Regenerate with `uv run python scripts/generate_models.py`.
# Value constraints are stripped on purpose; see that script.

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, RootModel
from typing import Any, Dict, Literal


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
        extra='allow',
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
        extra='allow',
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
        extra='allow',
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
        extra='allow',
    )
    url: str
    """
    Public HTTP or HTTPS URL for an MP4 video.
    """


class VideoBase64Ref(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    b64_json: str = Field(..., json_schema_extra={'contentEncoding': 'base64'})
    """
    Base64-encoded MP4 bytes, sent inline with the request.
    Bounded by the 2 MB request body limit, not by the 50 MB file limit: base64 costs a third more than the bytes it carries, so the largest clip that fits inline is roughly 1.5 MB. That is well under a typical 15-second render. Use `url` for anything larger -- a body over the limit is rejected with 413, which is a transport failure rather than a validation one and so is not in this endpoint's error list.
    """


class VideoUploadRef(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    upload_id: str
    """
    The `video_id` of a video you uploaded and whose status has reached `ready`. See `POST /v1/videos`.
    """


class VideoRef(RootModel[VideoUrlRef | VideoUploadRef | VideoBase64Ref]):
    root: VideoUrlRef | VideoUploadRef | VideoBase64Ref
    """
    How to give us the video. Exactly one of the three, and the choice is mostly about size.
    `upload_id` is the general answer: upload the file first (three calls, one of them straight to storage -- see `POST /v1/videos`) and reference it here. It is the only option that both reaches the 50 MB file limit and keeps the video private to your account.
    `url` is the shortcut when the video is already hosted somewhere we can GET. Note that it has to be publicly reachable; we send no credentials.
    `b64_json` sends the bytes inline. Convenient for a small local file, but bounded by the request body limit rather than the file limit -- see `POST /v1/evaluations`.
    """


class EvaluationCreate(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    model: ModelId | None = None
    model_version: str | None = None
    """
    Concrete model version to run. The deployment default applies when omitted.
    """
    prompt: str | None = None
    """
    Required when prompt-misalignment detection runs.
    """
    video: VideoRef
    glitch_types: list[GlitchType] | None = None
    metadata: dict[str, Any] | None = None
    """
    JSON metadata echoed on the evaluation. Serialized size must not exceed 8192 bytes.
    """


class TimePoint(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    frame: int
    sec: float
    timecode: str


class BoundingBox(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    xmin: float
    ymin: float
    xmax: float
    ymax: float


class BoxKeyframe(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    frame: int
    sec: float
    box: BoundingBox


class GlitchRegion(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    start: TimePoint
    end: TimePoint
    boxes: list[BoxKeyframe]


class PromptSegment(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    text: str
    char_start: int
    char_end: int


class Source(Enum):
    """
    Who produced this finding. Absent means the model, which is the common case -- the field is only set explicitly where a human annotated something the model missed, so treat its absence as `model` rather than as unknown.
    Deliberately NOT declared with a `default`. A default reads to a code generator as "the server always sends this", and it does not: the value is omitted, not defaulted, and a generated type that made it required would be wrong on almost every finding.
    """

    model = 'model'
    human = 'human'


class Glitch(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    id: str
    type: GlitchType
    description: str
    prompt_segment: PromptSegment | None = None
    """
    The prompt span this finding is about. `prompt_misalignment` only.
    NULL, not absent, on a `visual_glitch`. The service sends the key with a null value rather than omitting it, and this schema says so because a contract that quietly disagreed with the wire would be worse than an ugly one. Check for a value, not for the key.
    """
    region: GlitchRegion | None = None
    """
    Where in the video this finding is. Public for `visual_glitch`.
    NULL on a `prompt_misalignment`: the service produces one but it is not stable enough to publish, so it is withheld — as a null value, not an absent key.
    """
    source: Source | None = None
    """
    Who produced this finding. Absent means the model, which is the common case -- the field is only set explicitly where a human annotated something the model missed, so treat its absence as `model` rather than as unknown.
    Deliberately NOT declared with a `default`. A default reads to a code generator as "the server always sends this", and it does not: the value is omitted, not defaulted, and a generated type that made it required would be wrong on almost every finding.
    """
    severity: int | None = None
    """
    NULL on a `visual_glitch` -- the key is sent with a null value rather than omitted, so test the value.
    How far a prompt requirement was from being realized: `6 - score`, so 1 is a minor mismatch and 5 means the requirement is absent entirely. This is also the number the reporting threshold reads, so a finding you receive is by definition one that cleared it.
    In practice this is a `prompt_misalignment` field. The visual detector does not score its findings, so a `visual_glitch` normally has no `severity` at all; where one does appear it came from an older pipeline and grades the defect rather than a requirement. Either way it is optional — branch on `type` and handle its absence rather than assuming a default.
    """


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    num_glitches: int
    has_visual_glitch: bool
    has_prompt_misalignment: bool


class VideoInfo(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    duration_sec: float
    width: int
    height: int
    fps: float
    num_frames: int


class EvaluationUsage(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    video_seconds: float
    billable_units: float


class DetectorError(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    code: str
    message: str


class DetectorState(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    detector: GlitchType
    status: DetectorStatus
    error: DetectorError | None = None


class EvaluationResult(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    glitches: list[Glitch]
    summary: EvaluationSummary


class EvaluationFailure(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    type: str
    code: str
    message: str
    request_id: str


class Input(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    prompt: str
    video: VideoInfo


class Evaluation(BaseModel):
    model_config = ConfigDict(
        extra='allow',
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
    retry_of: str | None = None
    """
    The failed evaluation this one was filed to replace, if any.
    """
    retried_by: str | None = None
    """
    The evaluation filed to replace this one, if it has been retried.
    Set at most once, which is what makes retrying idempotent: a burst of presses claims this field exactly once, and every press that loses the race is handed the winner.
    """
    metadata: dict[str, Any] | None = None
    """
    Whatever you passed on create, echoed back. NULL when you passed nothing -- the key is always present, its value says whether there was any.
    Only found by submitting through the API. Every evaluation created in the console carries metadata, so a contract checked against console traffic alone looked correct here.
    """


class EvaluationCounts(BaseModel):
    """
    How many evaluations exist in each status, over the same owner and video scope as the request and deliberately IGNORING `limit`, `offset` and `status`.
    This is what a pager needs. Inferring the end of a list from "was the page full" is wrong at exactly the boundary paging exists to make honest, and a bare total could not tell you the page count for a filtered view.
    """

    model_config = ConfigDict(
        extra='allow',
    )
    __annotations__ = {
        '__pydantic_extra__': Dict[str, int],
    }
    queued: int | None = None
    processing: int | None = None
    completed: int | None = None
    partial: int | None = None
    failed: int | None = None


class EvaluationList(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    object: Literal['list']
    data: list[Evaluation]
    counts: EvaluationCounts | None = None


class RateLimitWindow(BaseModel):
    model_config = ConfigDict(
        extra='allow',
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
        extra='allow',
    )
    detect: RateLimitWindow
    generate: RateLimitWindow
    upload: RateLimitWindow


class QuotaReport(RateLimitWindow):
    model_config = ConfigDict(
        extra='allow',
    )
    scopes: QuotaScopes


class RateLimitDefinition(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    max: int
    window_sec: int


class ApiKeySummary(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    name: str
    prefix: str
    last4: str


class ModelBuild(BaseModel):
    model_config = ConfigDict(
        extra='allow',
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
        extra='allow',
    )
    formats: list[str]
    max_duration_sec: float
    max_file_bytes: int
    aspect_ratios: list[str]


class Model(BaseModel):
    model_config = ConfigDict(
        extra='allow',
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
        extra='allow',
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
        extra='allow',
    )
    visual_glitch: float | None = None
    prompt_misalignment: float | None = None


class PricingRates(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    per_second_per_detector: float
    per_second_by_detector: PerSecondByDetector | None = None
    cache_hit_rate: float
    assumed_duration_sec: float
    generation_from_catalog: bool | None = None


class Credits(BaseModel):
    model_config = ConfigDict(
        extra='allow',
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
        extra='allow',
    )
    key: str
    name: str
    description: str
    state: ComponentState
    detail: str
    latency_ms: float | None


class SystemStatus(BaseModel):
    model_config = ConfigDict(
        extra='allow',
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
        extra='allow',
    )
    type: ErrorType
    code: ErrorCode
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    error: Error
    quota: RateLimitWindow | None = None


class RateLimits(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    detect: RateLimitDefinition
    generate: RateLimitDefinition
    upload: RateLimitDefinition


class AccountLimits(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    requests_per_min: int
    window_sec: int
    max_concurrent_jobs: int
    rate_limits: RateLimits


class Account(BaseModel):
    model_config = ConfigDict(
        extra='allow',
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
