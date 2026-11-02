"""Claude deep analyzer with a fake streaming client: no network, no cost."""
import json
from pathlib import Path
from types import SimpleNamespace

from paper_analyst.analysis.deep_claude import REPORT_SCHEMA, ClaudeDeepAnalyzer, estimate_input_tokens
from paper_analyst.fulltext import Document, extract_pdf
from paper_analyst.report import REPORT_SECTIONS

DEMO = Path(__file__).resolve().parents[1] / "sample_data" / "demo_paper.pdf"


class _Stream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.response


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _Stream(self.response)


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)
        self.beta = SimpleNamespace(messages=self.messages)


def _resp(payload, stop="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop, model="claude-opus-5-5", content=[SimpleNamespace(type="text", text=text)])


def _bid(doc, start):
    return next(b.id for b in doc.blocks if b.text.startswith(start))


def test_schema():
    assert set(REPORT_SCHEMA["required"]) == set(REPORT_SECTIONS)


def test_validated_and_locators_from_document():
    doc = extract_pdf(DEMO)
    res = _bid(doc, "Table 1 summarizes")
    payload = {k: [] for k in REPORT_SECTIONS}
    payload["findings"] = [
        {"kind": "evidence", "text": "We find that the transferred SDF reduces the root-mean-squared pricing error by 14%",
         "block_ids": [res], "basis": ""},
        {"kind": "evidence", "text": "The SDF earns a Sharpe ratio of 1.8.", "block_ids": [res], "basis": ""},
        {"kind": "interpretation", "text": "The improvement of 14% is modest relative to its t-statistic of 2.9.",
         "block_ids": [res], "basis": "Results paragraph"},
        {"kind": "interpretation", "text": "This confirms Cochrane (2005).", "block_ids": [res], "basis": "x"},
    ]
    payload["open_questions"] = [{"kind": "speculation", "text": "Apply to corporate bonds.", "block_ids": [],
                                  "basis": "beyond the paper"}]
    client = FakeClient(_resp(payload))
    r = ClaudeDeepAnalyzer(client=client).analyze(doc, paper_id=1)
    kept = [(i.kind, i.text) for i in r.sections["findings"]]
    assert len(kept) == 2 and kept[0][0] == "evidence" and kept[1][0] == "interpretation"
    assert r.sections["findings"][0].locators[0].page == 2
    assert r.audit["dropped"] == 2
    assert r.sections["open_questions"][0].kind == "speculation"
    call = client.messages.calls[0]
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"]["schema"] is REPORT_SCHEMA
    assert f"[{res} | p.2 | §6 Empirical Results (results) | paragraph]" in call["messages"][0]["content"]
    assert r.connections and r.coverage["present"]


def test_refusal_bad_json_and_empty_doc():
    doc = extract_pdf(DEMO)
    r = ClaudeDeepAnalyzer(client=FakeClient(_resp("", stop="refusal"))).analyze(doc)
    assert any("declined" in w for w in r.validation_warnings)
    r = ClaudeDeepAnalyzer(client=FakeClient(_resp("nope"))).analyze(doc)
    assert any("non-JSON" in w for w in r.validation_warnings)
    client = FakeClient(_resp("{}"))
    ClaudeDeepAnalyzer(client=client).analyze(Document(source_path=None, source_type="text"))
    assert client.messages.calls == []


def test_without_fallbacks_and_token_estimate():
    doc = extract_pdf(DEMO)
    client = FakeClient(_resp({k: [] for k in REPORT_SECTIONS}))
    ClaudeDeepAnalyzer(client=client, use_fallbacks=False, model="claude-sonnet-5-5").analyze(doc)
    assert "fallbacks" not in client.messages.calls[0]
    assert 1000 < estimate_input_tokens(doc) < 20000
