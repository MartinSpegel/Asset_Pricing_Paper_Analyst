import pytest

from paper_analyst.models import Paper


def test_upsert_merges_duplicates(store):
    pid, created = store.upsert(Paper(title="A Paper About Pricing Kernels", doi="10.1/ABC", sources=["openalex"]))
    assert created
    pid2, created2 = store.upsert(Paper(title="A paper about pricing kernels", arxiv_id="2101.00001v1",
                                        abstract="Abstract text.", sources=["arxiv"]))
    assert pid2 == pid and not created2
    p = store.get(pid)
    assert p.doi == "10.1/abc" and p.arxiv_id == "2101.00001"
    assert p.abstract == "Abstract text." and p.sources == ["arxiv", "openalex"]
    assert store.count() == 1


def test_status_notes_and_listing(store):
    a, _ = store.upsert(Paper(title="First paper for listing test", relevance_score=10))
    b, _ = store.upsert(Paper(title="Second paper for listing test", relevance_score=90))
    assert [p.id for p in store.list()] == [b, a]
    store.set_status(a, "reading")
    store.set_notes(a, "Check robustness tables")
    assert [p.id for p in store.list(status="reading")] == [a]
    assert store.get(a).notes == "Check robustness tables"
    assert store.status_counts() == {"new": 1, "reading": 1}
    with pytest.raises(ValueError):
        store.set_status(a, "bogus")
    with pytest.raises(KeyError):
        store.set_status(999, "reading")


def test_analysis_roundtrip(store):
    pid, _ = store.upsert(Paper(title="Paper with an analysis attached"))
    store.save_analysis(pid, "heuristic", None, {"k": 1}, "# md")
    store.save_analysis(pid, "heuristic", None, {"k": 2}, "# md2")
    a = store.latest_analysis(pid)
    assert a["memo_json"] == {"k": 2} and a["memo_markdown"] == "# md2"


def test_persistence(tmp_path):
    from paper_analyst.storage import Store
    path = tmp_path / "x.db"
    with Store(path) as s:
        s.upsert(Paper(title="Persistent paper title here", authors=["A B"], urls={"pdf": "u"}))
    with Store(path) as s:
        p = s.list()[0]
        assert p.authors == ["A B"] and p.urls == {"pdf": "u"}
