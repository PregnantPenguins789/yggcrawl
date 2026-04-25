import main


def test_main_happy_path(monkeypatch, tmp_path):
    calls = {
        "indexed": [],
        "saved": False,
        "archived": False,
        "loaded": False,
        "diffed": False,
    }

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
        def validate_diff(self, diff):
            return True

        def load_snapshot(self):
            calls["loaded"] = True
            return {"records": []}

        def add_record(self, url, content):
            calls["indexed"].append((url, content))

        def diff_against(self, previous_snapshot):
            calls["diffed"] = True
            return {
                "new": ["http://example.com"],
                "changed": [],
                "unchanged": [],
            }

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "fakehash"

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)

    main.main()

    assert calls["loaded"] is True
    assert calls["indexed"] == [("http://example.com", "<html>ok</html>")]
    assert calls["diffed"] is True
    assert calls["saved"] is True
    assert calls["archived"] is True


def test_main_skips_diff_when_no_previous_snapshot(monkeypatch, tmp_path):
    calls = {
        "indexed": [],
        "saved": False,
        "archived": False,
        "loaded": False,
        "diffed": False,
    }

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
        def validate_diff(self, diff):
            return True

        def load_snapshot(self):
            calls["loaded"] = True
            return None

        def add_record(self, url, content):
            calls["indexed"].append((url, content))

        def diff_against(self, previous_snapshot):
            calls["diffed"] = True
            return {"new": [], "changed": [], "unchanged": []}

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "fakehash"

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)

    main.main()

    assert calls["loaded"] is True
    assert calls["indexed"] == [("http://example.com", "<html>ok</html>")]
    assert calls["diffed"] is False
    assert calls["saved"] is True
    assert calls["archived"] is True


def test_main_skips_failed_fetch(monkeypatch, tmp_path):
    calls = {
        "indexed": [],
        "saved": False,
        "archived": False,
        "loaded": False,
        "diffed": False,
    }

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
            return "<html>ignored</html>"

        def extract_links(self, content, url):
            return []

        def enqueue_links(self, links):
            pass

    class FakeIndexer:
        def validate_diff(self, diff):
            return True

        def load_snapshot(self):
            calls["loaded"] = True
            return {"records": []}

        def add_record(self, url, content):
            calls["indexed"].append((url, content))

        def diff_against(self, previous_snapshot):
            calls["diffed"] = True
            return {
                "new": [],
                "changed": [],
                "unchanged": [],
            }

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "fakehash"

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return None, "boom"

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)

    main.main()

    assert calls["loaded"] is True
    assert calls["indexed"] == []
    assert calls["diffed"] is True
    assert calls["saved"] is True
    assert calls["archived"] is True


def test_main_uses_bounded_queue(monkeypatch, tmp_path):
    calls = {
        "indexed": [],
        "saved": False,
        "archived": False,
    }

    monkeypatch.setattr(main, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MAX_URLS_PER_RUN", 2)

    class FakeCrawler:
        def __init__(self):
            self.urls = [
                "http://example.com/a",
                "http://example.com/b",
                "http://example.com/c",
            ]

        def next_url(self):
            if not self.urls:
                return None
            return self.urls.pop(0)

        def fetch(self, url):
            return "<html></html>"

        def extract_links(self, content, url):
            return []

        def enqueue_links(self, links):
            pass

    class FakeIndexer:
        def load_snapshot(self):
            return None

        def add_record(self, url, content):
            calls["indexed"].append((url, content))

        def validate_diff(self, diff):
            return True

        def diff_against(self, previous_snapshot):
            return {"new": [], "changed": [], "unchanged": []}

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "fakehash"

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)

    main.main()

    assert len(calls["indexed"]) == 2
    assert calls["indexed"][0][0] == "http://example.com/a"
    assert calls["indexed"][1][0] == "http://example.com/b"
    assert calls["saved"] is True
    assert calls["archived"] is True


def test_main_enqueues_discovered_links_but_stays_bounded(monkeypatch, tmp_path):
    calls = {
        "indexed": [],
        "saved": False,
        "archived": False,
        "enqueued": [],
    }

    monkeypatch.setattr(main, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MAX_URLS_PER_RUN", 1)

    class FakeCrawler:
        def __init__(self):
            self.urls = ["http://example.com/start"]
            self.queue = ["http://example.com/start"]
            self.seen = {"http://example.com/start"}

        def next_url(self):
            if not self.urls:
                return None
            return self.urls.pop(0)

        def fetch(self, url):
            return '<a href="/a">A</a><a href="/b">B</a>'

        def extract_links(self, content, url):
            return ["http://example.com/a", "http://example.com/b"]

        def enqueue_links(self, links):
            calls["enqueued"].extend(links)

    class FakeIndexer:
        def load_snapshot(self):
            return None

        def add_record(self, url, content):
            calls["indexed"].append((url, content))

        def validate_diff(self, diff):
            return True

        def diff_against(self, previous_snapshot):
            return {"new": [], "changed": [], "unchanged": []}

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "fakehash"

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)

    main.main()

    assert len(calls["indexed"]) == 1
    assert calls["indexed"][0][0] == "http://example.com/start"
    assert calls["enqueued"] == [
        "http://example.com/a",
        "http://example.com/b",
    ]
    assert calls["saved"] is True
    assert calls["archived"] is True


def test_main_calls_sync_from_peers_when_peer_urls_provided(monkeypatch, tmp_path):
    calls = {
        "synced": False,
        "peer_urls": None,
        "saved": False,
        "archived": False,
    }

    monkeypatch.setattr(main, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MAX_URLS_PER_RUN", 1)

    class FakeCrawler:
        def __init__(self):
            self.urls = ["http://example.com"]
            self.queue = []
            self.seen = set()

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
            return None

        def add_record(self, url, content):
            pass

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "fakehash"

        def diff_against(self, previous_snapshot):
            return {"new": [], "changed": [], "unchanged": []}

    def fake_sync_from_peers(indexer, peer_urls):
        calls["synced"] = True
        calls["peer_urls"] = peer_urls
        return {
            "peers_total": len(peer_urls),
            "peers_ok": len(peer_urls),
            "peers_failed": 0,
            "peers_invalid": 0,
            "added": 0,
            "updated": 0,
            "ignored": 0,
        }

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)
    monkeypatch.setattr(main, "sync_from_peers", fake_sync_from_peers)

    main.main(peer_urls=["http://peer1:8080", "http://peer2:8080"])

    assert calls["synced"] is True
    assert calls["peer_urls"] == ["http://peer1:8080", "http://peer2:8080"]
    assert calls["saved"] is True
    assert calls["archived"] is True


def test_main_skips_sync_from_peers_when_peer_urls_empty(monkeypatch, tmp_path):
    calls = {
        "synced": False,
        "saved": False,
        "archived": False,
    }

    monkeypatch.setattr(main, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MAX_URLS_PER_RUN", 1)

    class FakeCrawler:
        def __init__(self):
            self.urls = ["http://example.com"]
            self.queue = []
            self.seen = set()

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
            return None

        def add_record(self, url, content):
            pass

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "fakehash"

        def diff_against(self, previous_snapshot):
            return {"new": [], "changed": [], "unchanged": []}

    def fake_sync_from_peers(indexer, peer_urls):
        calls["synced"] = True
        return {}

    class FakeSandbox:
        @staticmethod
        def run_isolated(func, *args, timeout=30):
            return func(*args), None

    monkeypatch.setattr(main, "Crawler", FakeCrawler)
    monkeypatch.setattr(main, "Indexer", FakeIndexer)
    monkeypatch.setattr(main, "Sandbox", FakeSandbox)
    monkeypatch.setattr(main, "sync_from_peers", fake_sync_from_peers)

    main.main(peer_urls=[])

    assert calls["synced"] is False
    assert calls["saved"] is True
    assert calls["archived"] is True