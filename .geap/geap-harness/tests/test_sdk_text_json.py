"""SDK backend recovers schema JSON emitted as text (Gemini 3 sometimes skips structured output)."""

from geap_harness.backends.sdk import _json_from_text


def test_fenced_nested_json():
    text = 'Here you go:\n```json\n{"summary": "s", "findings": [{"a": {"b": 1}}]}\n```\n'
    assert _json_from_text(text) == {"summary": "s", "findings": [{"a": {"b": 1}}]}


def test_bare_json():
    assert _json_from_text('noise {"summary": "s", "findings": []} tail') == {"summary": "s", "findings": []}


def test_no_json():
    assert _json_from_text("no json here") is None
    assert _json_from_text("") is None
