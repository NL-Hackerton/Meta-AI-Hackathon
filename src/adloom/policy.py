"""Local phrase screening; not a certification of Meta policy compliance."""

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import TypeAdapter

from adloom.schemas import DomainModel, Flag, Understanding


class Rule(DomainModel):
    id: str
    pattern: str
    replacement: str


RULE_BYTES = Path(__file__).with_name("policy_rules.yaml").read_bytes()
# JSON is a YAML subset; using it keeps this small rule table strictly typed.
RULES = TypeAdapter(tuple[Rule, ...]).validate_json(RULE_BYTES)
POLICY_DIGEST = hashlib.sha256(RULE_BYTES).hexdigest()


def check(fields: Mapping[str, str]) -> tuple[Flag, ...]:
    flags = []
    for field, text in fields.items():
        for rule in RULES:
            if re.search(rule.pattern, text, flags=re.IGNORECASE):
                flags.append(Flag(
                    field=field, original=text, rule_id=rule.id, severity="block",
                    rewrite=re.sub(rule.pattern, rule.replacement, text, flags=re.IGNORECASE),
                ))
    return tuple(flags)


def understanding_fields(value: Understanding) -> dict[str, str]:
    return {"primary_text": value.primary_text, "headline": value.headline,
            **{f"hook:{hook.id}": hook.text for hook in value.hook_candidates}}
