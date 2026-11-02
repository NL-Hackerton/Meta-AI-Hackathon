"""Local pre-check of ad copy against a small rule table drawn from Meta's Advertising Standards.

This is not Meta ad review: it only catches listed phrasings, and Meta still reviews every ad.
Rule sources and limits: docs/api_notes/policy.md.
"""

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from adloom.schemas import DomainModel, Flag, NonEmpty, Understanding

FieldKind = Literal["primary_text", "headline", "hook", "subtitle"]
# Subtitles come from the confirmed transcript and cannot be edited after render, so a block there
# would lock approval with no fix; they are reported as warnings instead.
UNEDITABLE_FIELDS: frozenset[str] = frozenset({"subtitle"})


class Rule(DomainModel):
    id: NonEmpty
    category: NonEmpty
    severity: Literal["warn", "block"]
    fields: tuple[FieldKind, ...]
    pattern: NonEmpty
    replacement: NonEmpty
    policy_url: NonEmpty


RULE_BYTES = Path(__file__).with_name("policy_rules.yaml").read_bytes()
# JSON is a YAML subset; using it keeps this small rule table strictly typed.
RULES = TypeAdapter(tuple[Rule, ...]).validate_json(RULE_BYTES)
POLICY_DIGEST = hashlib.sha256(RULE_BYTES).hexdigest()
_COMPILED = tuple((rule, re.compile(rule.pattern, re.IGNORECASE)) for rule in RULES)


def check(fields: Mapping[str, str]) -> tuple[Flag, ...]:
    flags = []
    for field, text in fields.items():
        kind = field.split(":", 1)[0]
        for rule, pattern in _COMPILED:
            if kind not in rule.fields or not pattern.search(text):
                continue
            flags.append(
                Flag(
                    field=field,
                    original=text,
                    rule_id=rule.id,
                    severity="warn" if kind in UNEDITABLE_FIELDS else rule.severity,
                    rewrite=pattern.sub(rule.replacement.replace("\\", "\\\\"), text),
                )
            )
    return tuple(flags)


def understanding_fields(value: Understanding) -> dict[str, str]:
    return {
        "primary_text": value.primary_text,
        "headline": value.headline,
        **{f"hook:{hook.id}": hook.text for hook in value.hook_candidates},
    }
