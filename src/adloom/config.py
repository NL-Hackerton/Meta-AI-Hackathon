"""Environment configuration and explicit offline execution boundary."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from adloom.schemas import ErrorCode, ErrorDetail, Stage

ASPECTS: tuple[Literal["9:16", "4:5", "1:1"], ...] = ("9:16", "4:5", "1:1")
MAX_INPUT_SEC = 45
MAX_AD_SEC = 30
MAX_HOOK_CHARS = 22
MAX_STEP_PX = 24.0
BBOX_MARGIN = 0.06
SAFE_TOP = 0.14
SAFE_BOTTOM = 0.22
ALLOWED_CTAS = ("LEARN_MORE",)
FONT_PATH = (
    Path(__file__).resolve().parents[2] / "third_party/fonts/noto-sans-kr/NotoSansKR[wght].ttf"
)


class AdLoomError(Exception):
    def __init__(self, code: ErrorCode, stage: Stage, detail: str, retryable: bool = False) -> None:
        self.error = ErrorDetail(code=code, stage=stage, retryable=retryable, detail=detail)
        super().__init__(f"{code}: {detail}")


SPARK_MODEL: Literal["muse-spark-1.3"] = "muse-spark-1.3"
LIVE_REQUIRED_ENV = (
    "MODEL_API_KEY",
    "META_ACCESS_TOKEN",
    "META_AD_ACCOUNT_ID",
    "META_PAGE_ID",
    "META_GRAPH_VERSION",
)


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Secret fields never appear in repr, equality or pickles."""

    data_dir: Path
    mode: Literal["fixture", "live"] = "fixture"
    spark_model: Literal["muse-spark-1.3"] = SPARK_MODEL
    model_api_key: str | None = field(default=None, repr=False, compare=False)
    meta_access_token: str | None = field(default=None, repr=False, compare=False)
    meta_ad_account_id: str | None = None
    meta_page_id: str | None = None
    meta_graph_version: str | None = None
    spend_limit_usd: Decimal | None = None

    def __reduce__(self) -> str | tuple[object, ...]:
        raise TypeError("Settings carry secrets and are never serialized")


def live_settings_from_env(env: Mapping[str, str]) -> Settings:
    """Validate the live environment without contacting any service.

    Errors name missing or malformed variables, never their values.
    """
    if env.get("ADLOOM_SPARK_MODEL", SPARK_MODEL) != SPARK_MODEL:
        raise AdLoomError("E_INPUT_INVALID", "input", "Only the Standard Spark model is allowed")
    missing = [name for name in LIVE_REQUIRED_ENV if not env.get(name, "").strip()]
    if missing:
        raise AdLoomError("E_API_AUTH", "input", f"Live execution requires: {', '.join(missing)}")
    invalid: list[str] = []
    account = env["META_AD_ACCOUNT_ID"].strip()
    page = env["META_PAGE_ID"].strip()
    version = env["META_GRAPH_VERSION"].strip()
    if not re.fullmatch(r"act_[0-9]+", account, re.ASCII):
        invalid.append("META_AD_ACCOUNT_ID (expected act_<digits>)")
    if not re.fullmatch(r"[0-9]+", page, re.ASCII):
        invalid.append("META_PAGE_ID (expected digits)")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version, re.ASCII):
        invalid.append("META_GRAPH_VERSION (expected a pinned vMAJOR.MINOR version)")
    limit: Decimal | None = None
    raw_limit = env.get("ADLOOM_SPEND_LIMIT_USD", "").strip()
    if raw_limit:
        try:
            limit = Decimal(raw_limit)
        except InvalidOperation:
            limit = None
        if limit is None or not limit.is_finite() or limit <= 0:
            invalid.append("ADLOOM_SPEND_LIMIT_USD (expected a positive amount)")
            limit = None
    if invalid:
        raise AdLoomError("E_API_AUTH", "input", f"Invalid live settings: {'; '.join(invalid)}")
    return Settings(
        data_dir=Path(env.get("ADLOOM_DATA_DIR", "data")).resolve(),
        mode="live",
        model_api_key=env["MODEL_API_KEY"].strip(),
        meta_access_token=env["META_ACCESS_TOKEN"].strip(),
        meta_ad_account_id=account,
        meta_page_id=page,
        meta_graph_version=version,
        spend_limit_usd=limit,
    )


def require_live_ready(settings: Settings, stage: Stage = "input") -> None:
    """Refuse a live run that lacks credentials or the H2 spending limit."""
    if settings.mode != "live":
        return
    if settings.spend_limit_usd is None:
        raise AdLoomError(
            "E_API_AUTH", stage, "Set a spending limit (ADLOOM_SPEND_LIMIT_USD) before live runs"
        )
    absent = [
        name
        for name, value in (
            ("MODEL_API_KEY", settings.model_api_key),
            ("META_ACCESS_TOKEN", settings.meta_access_token),
            ("META_AD_ACCOUNT_ID", settings.meta_ad_account_id),
            ("META_PAGE_ID", settings.meta_page_id),
            ("META_GRAPH_VERSION", settings.meta_graph_version),
        )
        if not value
    ]
    if absent:
        raise AdLoomError("E_API_AUTH", stage, f"Live execution requires: {', '.join(absent)}")


def load_config(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    if env.get("ADLOOM_SPARK_MODEL", SPARK_MODEL) != SPARK_MODEL:
        raise AdLoomError("E_INPUT_INVALID", "input", "Only the Standard Spark model is allowed")
    live = env.get("ADLOOM_LIVE", "0")
    if live not in {"0", "1"}:
        raise AdLoomError("E_INPUT_INVALID", "input", "ADLOOM_LIVE must be 0 or 1")
    if live == "1":
        # The single live gate. Remove only after the H2/H3 approvals are recorded; then
        # return live_settings_from_env(env). Never downgrade a live request to fixtures.
        raise AdLoomError("E_API_AUTH", "input", "Live execution requires H2/H3 approval")
    return Settings(data_dir=Path(env.get("ADLOOM_DATA_DIR", "data")).resolve())
