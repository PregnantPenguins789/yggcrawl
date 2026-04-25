import json
import main


def test_invalid_diff_not_written(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MAX_URLS_PER_RUN", 10)

    class FakeCrawler:
        def __init__(self):
            self.urls = ["http://example.com"]

        def next_url(self):
            if not self.urls:
                return None
            return self.urls.pop(0)

        def fetch(self, url):
            return "<html>ok</html>"

        def extract_links(self, content, url):
            return []

        def enqueue_links(self, links):
            pass

    class FakeIndexer:
        def load_snapshot(self):
            return {"records": []}

        def add_record(self, url, content):
            pass

        def diff_against(self, previous_snapshot):
            return {"bad": "format"}

        def validate_diff(self, diff):
            return False

        def save_snapshot(self):
            return "hash"

        def archive_snapshot(self):
            pass

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)

    main.main()

    diff_file = tmp_path / "diff.json"
    assert not diff_file.exists()


def test_diff_file_written_with_changed_url(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MAX_URLS_PER_RUN", 10)

    class FakeCrawler:
        def __init__(self):
            self.urls = ["http://example.com"]

        def next_url(self):
            if not self.urls:
                return None
            return self.urls.pop(0)

        def fetch(self, url):
            return "<html>changed</html>"

        def extract_links(self, content, url):
            return []

        def enqueue_links(self, links):
            pass

    class FakeIndexer:
        def load_snapshot(self):
            return {"records": [{"url": "http://example.com", "content_hash": "old"}]}

        def add_record(self, url, content):
            pass

        def diff_against(self, previous_snapshot):
            return {
                "new": [],
                "changed": ["http://example.com"],
                "unchanged": [],
            }

        def validate_diff(self, diff):
            return True

        def save_snapshot(self):
            return "hash"

        def archive_snapshot(self):
            pass

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)

    main.main()

    diff_file = tmp_path / "diff.json"
    assert diff_file.exists()

    data = json.loads(diff_file.read_text())
    assert data["new"] == []
    assert data["changed"] == ["http://example.com"]
    assert data["unchanged"] == []