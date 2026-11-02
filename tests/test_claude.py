"""Tests for the optional Claude analyzer using a fake client (no network, no cost)."""
import json
from types import SimpleNamespace

from paper_analyst.analysis.claude import MEMO_SCHEMA, ClaudeAnalyzer
from paper_analyst.memo import SECTIONS


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)
        self.beta = SimpleNamespace(messages=self.messages)


def _response(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5-5",
                           content=[SimpleNamespace(type="text", text=text)])


def _payload(**overrides):
    d = {k: {"claims": [], "interpretations": []} for k in SECTIONS}
    d.update(overrides)
    return d


def test_schema_covers_all_sections():
    assert set(MEMO_SCHEMA["required"]) == set(SECTIONS)
    assert MEMO_SCHEMA["additionalProperties"] is False


def test_claude_memo_validated_against_source(sample_paper):
    payload = _payload(
        results={"claims": ["We find that pricing errors fall by 10%.",
                            "The SDF earns a Sharpe ratio of 2.0."],  # hallucinated -> dropped
                 "interpretations": [{"text": "Gains may reflect shared risk premia.",
                                      "basis": "Inference from the results sentence."}]})
    client = FakeClient(_response(payload))
    memo = ClaudeAnalyzer(client=client).analyze(sample_paper)
    assert [c.text for c in memo.sections["results"].claims] == ["We find that pricing errors fall by 10%."]
    assert memo.sections["results"].interpretations[0].text.startswith("Gains may")
    assert any("Sharpe ratio of 2.0" in w for w in memo.warnings)
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert sample_paper.abstract in call["messages"][0]["content"]


def test_claude_without_fallbacks_uses_standard_endpoint(sample_paper):
    client = FakeClient(_response(_payload()))
    ClaudeAnalyzer(client=client, use_fallbacks=False, model="claude-sonnet-5-5").analyze(sample_paper)
    call = client.messages.calls[0]
    assert "fallbacks" not in call and call["model"] == "claude-sonnet-5-5"


def test_claude_refusal_and_bad_json(sample_paper):
    memo = ClaudeAnalyzer(client=FakeClient(_response("", stop_reason="refusal"))).analyze(sample_paper)
    assert any("declined" in w for w in memo.warnings)
    memo = ClaudeAnalyzer(client=FakeClient(_response("not json"))).analyze(sample_paper)
    assert any("non-JSON" in w for w in memo.warnings)


def test_claude_not_called_without_source():
    from paper_analyst.models import Paper
    client = FakeClient(_response(_payload()))
    memo = ClaudeAnalyzer(client=client).analyze(Paper(title="empty"))
    assert client.messages.calls == [] and memo.warnings
