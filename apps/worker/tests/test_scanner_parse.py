"""Tests for the scanner's LLM response parser.

The model is told to output a JSON array, but real-world responses often
preamble with prose or wrap the array in markdown fences. _parse_signals
needs to find the array regardless.
"""

from maelstrom_worker.scanner import _extract_json_array, _parse_signals


def test_extract_pure_json() -> None:
    assert _extract_json_array('[{"symbol":"BTC-PERP"}]') == '[{"symbol":"BTC-PERP"}]'


def test_extract_fenced_json() -> None:
    text = '```json\n[{"symbol":"BTC-PERP"}]\n```'
    assert _extract_json_array(text) == '[{"symbol":"BTC-PERP"}]'


def test_extract_unfenced_code_block() -> None:
    text = '```\n[{"a":1}]\n```'
    assert _extract_json_array(text) == '[{"a":1}]'


def test_extract_preamble_then_array() -> None:
    text = (
        "Looking at the data, I see two interesting movers.\n\n"
        "Here is the JSON:\n"
        '[{"symbol":"BTC-PERP","direction":"long","score":50,"source":"binance"}]'
    )
    extracted = _extract_json_array(text)
    assert extracted is not None
    assert extracted.startswith("[")
    assert "BTC-PERP" in extracted


def test_extract_string_with_brackets_inside() -> None:
    # The opening bracket lives inside a string; our walker must not pick it.
    text = 'No JSON here, just "this [is in a string]".'
    assert _extract_json_array(text) is None


def test_extract_empty_array_in_prose() -> None:
    text = "I find nothing compelling.\nResult: []"
    assert _extract_json_array(text) == "[]"


def test_parse_with_preamble() -> None:
    raw = (
        "Analysis: AAVE is the strongest mover.\n\n"
        "```json\n"
        '[{"symbol":"AAVE-PERP","direction":"long","source":"binance",'
        '"score":70,"confidence":0.7,"horizon":"intraday","rationale":"momentum"}]\n'
        "```"
    )
    signals = _parse_signals(raw)
    assert len(signals) == 1
    assert signals[0]["symbol"] == "AAVE-PERP"
    assert signals[0]["direction"] == "long"
    assert signals[0]["score"] == 70


def test_parse_garbage_returns_empty() -> None:
    assert _parse_signals("nothing JSON-like at all") == []


def test_parse_array_with_invalid_items_filters_them() -> None:
    raw = (
        '[{"symbol":"BTC-PERP","direction":"long","source":"binance"},'
        '{"not_a_symbol":true},'
        '{"symbol":"ETH-PERP","direction":"invalid_dir"}]'
    )
    signals = _parse_signals(raw)
    assert len(signals) == 1
    assert signals[0]["symbol"] == "BTC-PERP"
