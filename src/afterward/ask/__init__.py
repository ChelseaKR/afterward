"""The optional runtime AI service: AI at the edges, the published dataset as the only evidence.

Recorded in ``docs/adr/0003-runtime-ai-at-the-edges.md``. The shape is fixed there and every
module here keeps to it:

- :mod:`afterward.ask.dataset` loads the published dataset and resolves free-text terms
  against its own vocabulary. Nothing here is allowed to guess a SOC code or a region name.
- :mod:`afterward.ask.query` is the structured query the model may produce and the
  deterministic executor that runs it. The model structures; this module finds.
- :mod:`afterward.ask.evidence` renders the records that were found as facts with record
  ids, saying "not reported" where the dataset says null.
- :mod:`afterward.ask.narrate` asks the model to narrate those facts as claims that cite
  record ids and declare the numbers they use.
- :mod:`afterward.ask.verify` checks every claim against the published JSON and withholds
  what does not verify. It is the only thing between the model and the reader.
- :mod:`afterward.ask.provider` is the one place the ``anthropic`` SDK is called.
"""

from __future__ import annotations

PROMPT_VERSION = "2026-08-21.2"
"""Stamped on every response and every eval result. Bump when any prompt text changes."""

PROMPT_DIGEST = "7a86c6bf0db8b4219a8b7e864bce6970adacefbf530e9faeb8bb0d7e058e30fb"
"""SHA-256 over every system prompt, pinned beside the version. ``tests/test_ask_prompts.py``
recomputes it, so a prompt edit that does not bump ``PROMPT_VERSION`` fails the build and
eval results stay comparable only within a version. Recompute with
``afterward.ask.prompts.digest()``."""
