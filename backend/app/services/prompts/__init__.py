"""Centralized, versioned system prompts for every AI surface.

Each module exports a `SYSTEM` string (or several, for modules serving more
than one function) plus a matching `VERSION` string. Bump the version any
time the prompt text changes meaningfully — callers fold the version into
their cache keys, so a prompt edit automatically invalidates previously
cached output instead of silently serving stale results generated under the
old instructions (the concall "Summary unavailable" cache-poisoning bug this
project hit earlier was exactly this class of problem).
"""
