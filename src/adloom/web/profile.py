"""Business profile for the local owner, stored beside the jobs in the data directory."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

from adloom.jobs import atomic_write


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _https(value: HttpUrl | None) -> HttpUrl | None:
    if value is not None and (
        value.scheme != "https" or value.username is not None or value.password is not None
    ):
        raise ValueError("destination must be an https URL without credentials")
    return value


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    business_name: Annotated[str, StringConstraints(max_length=60), AfterValidator(_not_blank)]
    category: Annotated[str, StringConstraints(max_length=40), AfterValidator(_not_blank)]
    region: Annotated[str, StringConstraints(max_length=60), AfterValidator(_not_blank)]
    daily_budget_krw: Annotated[int, Field(ge=1000, le=9_007_199_254_740_991)]
    destination_url: Annotated[HttpUrl | None, AfterValidator(_https)] = None
    language: Literal["ko", "en"]


def profile_path(data_dir: Path) -> Path:
    return data_dir / "profile.json"


def load_profile(data_dir: Path) -> Profile | None:
    path = profile_path(data_dir)
    if not path.is_file():
        return None
    return Profile.model_validate_json(path.read_bytes())


def save_profile(data_dir: Path, profile: Profile) -> Profile:
    atomic_write(profile_path(data_dir), profile.model_dump_json().encode())
    return profile
