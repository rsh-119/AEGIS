"""backend/.env.example must stay in step with Settings.

The previous validation checked this once, by hand, and reported it as verified
— which is exactly how it drifts again. `.env.example` is the only place an
operator learns that a setting exists, and the one that went missing last time
(INDIANAPI_KEY) was the sole market-data credential: without it the app starts
cleanly and serves no market data at all. So this is asserted in BOTH
directions, on every run:

  • every Settings field is documented, so a new setting cannot ship invisibly
  • every documented key is a real Settings field, so a renamed or deleted
    setting cannot linger as advice that silently does nothing

Fields that legitimately must not appear are listed in _NOT_DOCUMENTED with a
reason each.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

# Settings fields deliberately absent from .env.example.
_NOT_DOCUMENTED: dict[str, str] = {
    # Reserved for a future OAuth authorization-code flow; the ID-token flow
    # this app uses never reads it, so documenting it would invite operators to
    # go find a value they do not need.
    "google_client_secret": "unused by the ID-token flow — reserved, not required",
}


def _documented_keys() -> set[str]:
    """Every KEY= that appears at the start of a line (commented-out examples
    do not count as documentation — an operator cannot set what is commented)."""
    text = ENV_EXAMPLE.read_text()
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))


def test_env_example_exists():
    assert ENV_EXAMPLE.is_file(), f"{ENV_EXAMPLE} is missing"


def test_every_setting_is_documented():
    fields = set(Settings.model_fields)
    documented = {k.lower() for k in _documented_keys()}
    missing = fields - documented - set(_NOT_DOCUMENTED)
    assert not missing, (
        "these Settings fields are not in backend/.env.example, so an operator "
        f"has no way to discover them: {sorted(missing)}"
    )


def test_no_documented_key_is_a_dead_setting():
    fields = set(Settings.model_fields)
    stray = {k for k in _documented_keys() if k.lower() not in fields}
    assert not stray, (
        "backend/.env.example documents keys that are not Settings fields — "
        f"setting them does nothing: {sorted(stray)}"
    )


def test_exclusions_are_still_real_fields():
    """Guard the guard: an exclusion for a field that no longer exists would
    quietly mask a genuinely undocumented setting of the same name later."""
    gone = set(_NOT_DOCUMENTED) - set(Settings.model_fields)
    assert not gone, f"_NOT_DOCUMENTED lists fields that no longer exist: {sorted(gone)}"


def test_no_real_secret_values_are_committed_in_the_example():
    """Placeholders only. A real key here would be a committed credential."""
    text = ENV_EXAMPLE.read_text()
    for line in text.splitlines():
        if not re.match(r"^[A-Z][A-Z0-9_]*=", line):
            continue
        key, _, value = line.partition("=")
        if not value.strip():
            continue
        if not any(t in key for t in ("KEY", "SECRET", "TOKEN", "PASSWORD", "DSN")):
            continue
        assert value.startswith("your_") or value in ("", "false", "true"), (
            f"{key} in .env.example looks like a real value, not a placeholder"
        )
