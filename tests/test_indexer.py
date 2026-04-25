from indexer import Indexer

def test_add_record():
    idx = Indexer()
    idx.add_record("http://example.com", "<html>ok</html>")
    assert len(idx.records) == 1
    assert idx.records[0]["url"] == "http://example.com"
    assert "content_hash" in idx.records[0]