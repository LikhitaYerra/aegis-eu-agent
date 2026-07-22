"""Reasoning and critic-response regression tests."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reasoning import parse_critic_response


def test_parses_markdown_wrapped_critic_json() -> None:
    response = """```json
{"verdict":"PASS","issues":[],"suggested_fix":"No changes required."}
```"""
    assert parse_critic_response(response) == "PASS: No changes required."


def test_parses_json_embedded_in_model_commentary() -> None:
    response = (
        'Review complete.\n{"verdict":"REVISE","issues":["citation"],'
        '"suggested_fix":"Add a source citation."}'
    )
    assert parse_critic_response(response) == "REVISE: Add a source citation."


def test_invalid_critic_payload_fails_closed() -> None:
    assert parse_critic_response("The answer looks fine.") == (
        "REVISE: Critic returned invalid JSON."
    )
    assert parse_critic_response('{"verdict":"APPROVE"}') == (
        "REVISE: Critic returned an invalid verdict."
    )
