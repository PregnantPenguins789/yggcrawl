import main


def test_run_once_preserves_single_run_orchestration(monkeypatch, tmp_path):
    calls = {
        "indexed": [],
        "saved": False,
        "archived": False,
        "loaded": False,
        "diffed": False,
        "synced": False,
    }

    monkeypatch.setattr(main, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(main, "MAX_URLS_PER_RUN", 10)
    monkeypatch.setattr(main, "validate_diff", lambda diff: True)

    def fake_sync_from_peers(indexer, peer_urls):
        calls["synced"] = True
        calls["peer_urls"] = list(peer_urls)

    monkeypatch.setattr(main, "sync_from_peers", fake_sync_from_peers)

    class FakeCrawler:
        def __init__(self):
            self.urls = ["http://example.com"]
            self.queue = []
            self.seen = {"http://example.com"}

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
            calls["loaded"] = True
            return {"records": []}

        def add_record(self, url, content):
            calls["indexed"].append((url, content))

        def diff_against(self, previous_snapshot):
            calls["diffed"] = True
            return {
                "new": [{"url": "http://example.com"}],
                "changed": [],
                "unchanged": [],
            }

        def save_snapshot(self):
            calls["saved"] = True
            calls["archived"] = True  # archiving happens inside save_snapshot
            return "abc123"

    crawler = FakeCrawler()
    indexer = FakeIndexer()

    main.run_once(indexer, crawler, ["http://peer1.test/snapshot.json"])

    assert calls["loaded"] is True
    assert calls["indexed"] == [("http://example.com", "<html>ok</html>")]
    assert calls["synced"] is True
    assert calls["peer_urls"] == ["http://peer1.test/snapshot.json"]
    assert calls["diffed"] is True
    assert calls["saved"] is True
    assert calls["archived"] is True
    assert (tmp_path / "diff.json").exists()


def test_run_loop_stops_at_max_runs(monkeypatch):
    calls = {
        "crawl": 0,
        "log": 0,
        "peer": 0,
        "load": 0,
        "diff": 0,
        "save": 0,
        "sleeps": [],
    }

    monkeypatch.setattr(
        main,
        "phase_local_crawl",
        lambda indexer, crawler: calls.__setitem__("crawl", calls["crawl"] + 1) or 1,
    )
    monkeypatch.setattr(
        main,
        "phase_log_crawl_status",
        lambda processed, crawler: calls.__setitem__("log", calls["log"] + 1),
    )
    monkeypatch.setattr(
        main,
        "phase_peer_sync",
        lambda indexer, peer_urls: calls.__setitem__("peer", calls["peer"] + 1),
    )
    monkeypatch.setattr(
        main,
        "phase_load_previous_snapshot",
        lambda indexer: calls.__setitem__("load", calls["load"] + 1) or {"records": []},
    )
    monkeypatch.setattr(
        main,
        "phase_diff_and_write",
        lambda indexer, previous_snapshot: calls.__setitem__("diff", calls["diff"] + 1),
    )
    monkeypatch.setattr(
        main,
        "phase_save_and_archive",
        lambda indexer: calls.__setitem__("save", calls["save"] + 1),
    )
    monkeypatch.setattr(main.time, "sleep", lambda seconds: calls["sleeps"].append(seconds))

    main.run_loop(
        indexer=object(),
        crawler=object(),
        peer_urls=["http://peer.test/snapshot.json"],
        max_runs=3,
        sleep_seconds=5,
    )

    assert calls["crawl"] == 3
    assert calls["log"] == 3
    assert calls["peer"] == 1
    assert calls["load"] == 1
    assert calls["diff"] == 1
    assert calls["save"] == 1
    assert calls["sleeps"] == [5, 5]


def test_run_loop_handles_keyboard_interrupt_cleanly(monkeypatch):
    calls = {
        "crawl": 0,
        "log": 0,
        "load": 0,
        "diff": 0,
        "save": 0,
        "logs": [],
    }

    monkeypatch.setattr(
        main,
        "phase_local_crawl",
        lambda indexer, crawler: calls.__setitem__("crawl", calls["crawl"] + 1) or 1,
    )
    monkeypatch.setattr(
        main,
        "phase_log_crawl_status",
        lambda processed, crawler: calls.__setitem__("log", calls["log"] + 1),
    )
    monkeypatch.setattr(
        main,
        "phase_load_previous_snapshot",
        lambda indexer: calls.__setitem__("load", calls["load"] + 1) or {"records": []},
    )
    monkeypatch.setattr(
        main,
        "phase_diff_and_write",
        lambda indexer, previous_snapshot: calls.__setitem__("diff", calls["diff"] + 1),
    )
    monkeypatch.setattr(
        main,
        "phase_save_and_archive",
        lambda indexer: calls.__setitem__("save", calls["save"] + 1),
    )
    monkeypatch.setattr(
        main.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    monkeypatch.setattr(main.logger, "info", lambda message: calls["logs"].append(message))

    main.run_loop(
        indexer=object(),
        crawler=object(),
        peer_urls=[],
        max_runs=None,
        sleep_seconds=5,
    )

    assert calls["crawl"] == 1
    assert calls["log"] == 1
    assert calls["load"] == 1
    assert calls["diff"] == 1
    assert calls["save"] == 1
    assert calls["logs"] == ["Continuous run interrupted; shutting down cleanly"]