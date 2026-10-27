"""Environment configuration and explicit offline execution boundary."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
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
FONT_PATH = Path(__file__).resolve().parents[2] / "third_party/fonts/noto-sans-kr/NotoSansKR[wght].ttf"


class AdLoomError(Exception):
    def __init__(
        self, code: ErrorCode, stage: Stage, detail: str, retryable: bool = False
    ) -> None:
        self.error = ErrorDetail(code=code, stage=stage, retryable=retryable, detail=detail)
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    mode: Literal["fixture"] = "fixture"
    spark_model: Literal["muse-spark-1.3"] = "muse-spark-1.3"


def load_config(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    if env.get("ADLOOM_SPARK_MODEL", "muse-spark-1.3") != "muse-spark-1.3":
        raise AdLoomError("E_INPUT_INVALID", "input", "Only the Standard Spark model is allowed")
    live = env.get("ADLOOM_LIVE", "0")
    if live not in {"0", "1"}:
        raise AdLoomError("E_INPUT_INVALID", "input", "ADLOOM_LIVE must be 0 or 1")
    if live == "1":
        # A general request to implement the product does not authorize external calls.
        # Never downgrade an explicit live request to synthetic output.
        raise AdLoomError("E_API_AUTH", "input", "Live execution requires H2/H3 approval")
    return Settings(data_dir=Path(env.get("ADLOOM_DATA_DIR", "data")).resolve())
