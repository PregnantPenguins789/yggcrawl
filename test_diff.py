from indexer import Indexer


def test_diff_against_all_new():
    idx = Indexer()
    idx.add_record("http://a.com", "<html>a</html>")
    idx.add_record("http://b.com", "<html>b</html>")

    previous = {"records": []}

    diff = idx.diff_against(previous)

    assert diff["new"] == ["http://a.com", "http://b.com"]
    assert diff["changed"] == []
    assert diff["unchanged"] == []


def test_diff_against_changed_and_unchanged():
    idx = Indexer()
    idx.add_record("http://a.com", "<html>a</html>")
    idx.add_record("http://b.com", "<html>new-b</html>")

    a_hash = next(r for r in idx.records if r["url"] == "http://a.com")["content_hash"]

    previous = {
        "records": [
            {
                "url": "http://a.com",
                "fetched_at": 1,
                "content_hash": a_hash,
            },
            {
                "url": "http://b.com",
                "fetched_at": 1,
                "content_hash": "deadbeef",
            },
        ]
    }

    diff = idx.diff_against(previous)

    assert diff["new"] == []
    assert diff["changed"] == ["http://b.com"]
    assert diff["unchanged"] == ["http://a.com"]


def test_diff_against_mixed():
    idx = Indexer()
    idx.add_record("http://a.com", "<html>a</html>")
    idx.add_record("http://b.com", "<html>b-new</html>")
    idx.add_record("http://c.com", "<html>c</html>")

    a_hash = next(r for r in idx.records if r["url"] == "http://a.com")["content_hash"]

    previous = {
        "records": [
            {
                "url": "http://a.com",
                "fetched_at": 1,
                "content_hash": a_hash,
            },
            {
                "url": "http://b.com",
                "fetched_at": 1,
                "content_hash": "deadbeef",
            },
        ]
    }

    diff = idx.diff_against(previous)

    assert diff["new"] == ["http://c.com"]
    assert diff["changed"] == ["http://b.com"]
    assert diff["unchanged"] == ["http://a.com"]