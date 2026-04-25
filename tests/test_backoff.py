import main


def test_peer_failure_backs_off_future_peer_attempts(monkeypatch):
    calls = {
        "crawl": 0,
        "peer": 0,
        "sleep": [],
    }

    monkeypatch.setattr(main, "phase_local_crawl", lambda indexer, crawler: 1)
    monkeypatch.setattr(main, "phase_log_crawl_status", lambda processed, crawler: None)
    monkeypatch.setattr(
        main,
        "phase_load_previous_snapshot",
        lambda indexer: {"records": []},
    )
    monkeypatch.setattr(
        main,
        "phase_diff_and_write",
        lambda indexer, previous_snapshot: None,
    )
    monkeypatch.setattr(
        main,
        "phase_save_and_archive",
        lambda indexer: None,
    )

    def fake_peer_sync(indexer, peer_urls):
        calls["peer"] += 1
        if calls["peer"] == 1:
            raise RuntimeError("peer down")

    monkeypatch.setattr(main, "phase_peer_sync", fake_peer_sync)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: calls["sleep"].append(seconds))

    main.run_loop(
        indexer=object(),
        crawler=object(),
        peer_urls=["http://peer.test/snapshot.json"],
        max_runs=3,
        sleep_seconds=5,
        sync_every=1,
        snapshot_every=100,
        max_backoff_iterations=32,
    )

    assert calls["peer"] == 2


def test_snapshot_failure_backs_off_future_snapshot_attempts(monkeypatch):
    calls = {
        "load": 0,
        "diff": 0,
        "save": 0,
        "sleep": [],
    }

    monkeypatch.setattr(main, "phase_local_crawl", lambda indexer, crawler: 1)
    monkeypatch.setattr(main, "phase_log_crawl_status", lambda processed, crawler: None)
    monkeypatch.setattr(main, "phase_peer_sync", lambda indexer, peer_urls: None)

    def fake_load_previous_snapshot(indexer):
        calls["load"] += 1
        if calls["load"] == 1:
            raise RuntimeError("disk busy")
        return {"records": []}

    monkeypatch.setattr(
        main,
        "phase_load_previous_snapshot",
        fake_load_previous_snapshot,
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
    monkeypatch.setattr(main.time, "sleep", lambda seconds: calls["sleep"].append(seconds))

    main.run_loop(
        indexer=object(),
        crawler=object(),
        peer_urls=[],
        max_runs=3,
        sleep_seconds=5,
        sync_every=100,
        snapshot_every=1,
        max_backoff_iterations=32,
    )

    assert calls["load"] == 2
    assert calls["diff"] == 1
    assert calls["save"] == 1


def test_peer_success_resets_backoff(monkeypatch):
    calls = {
        "peer": 0,
    }

    monkeypatch.setattr(main, "phase_local_crawl", lambda indexer, crawler: 1)
    monkeypatch.setattr(main, "phase_log_crawl_status", lambda processed, crawler: None)
    monkeypatch.setattr(
        main,
        "phase_load_previous_snapshot",
        lambda indexer: {"records": []},
    )
    monkeypatch.setattr(
        main,
        "phase_diff_and_write",
        lambda indexer, previous_snapshot: None,
    )
    monkeypatch.setattr(
        main,
        "phase_save_and_archive",
        lambda indexer: None,
    )

    def fake_peer_sync(indexer, peer_urls):
        calls["peer"] += 1
        if calls["peer"] == 1:
            raise RuntimeError("temporary peer failure")

    monkeypatch.setattr(main, "phase_peer_sync", fake_peer_sync)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)

    main.run_loop(
        indexer=object(),
        crawler=object(),
        peer_urls=["http://peer.test/snapshot.json"],
        max_runs=5,
        sleep_seconds=5,
        sync_every=1,
        snapshot_every=100,
        max_backoff_iterations=32,
    )

    assert calls["peer"] == 4