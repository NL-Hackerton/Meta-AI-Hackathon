from pathlib import Path

from pydantic import ValidationError

from adloom.adapters.base import UnderstandingAdapter
from adloom.config import ALLOWED_CTAS, AdLoomError
from adloom.policy import check, understanding_fields
from adloom.schemas import Understanding


def understand(
    video: Path, note_text: str, language: str, adapter: UnderstandingAdapter
) -> Understanding:
    feedback: str | None = None
    for _ in range(2):
        raw = adapter.understand(video, note_text, language, feedback)
        try:
            result = Understanding.model_validate_json(raw)
            if result.cta not in ALLOWED_CTAS:
                raise ValueError("CTA is not in the configured allowlist")
            return result.model_copy(update={"policy_flags": check(understanding_fields(result))})
        except (ValidationError, ValueError) as error:
            feedback = str(error)
    raise AdLoomError("E_API_SCHEMA", "understand", "Output invalid after one schema repair")
