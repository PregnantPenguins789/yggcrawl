import pytest
from unittest.mock import MagicMock
import main

def test_run_loop_gates_peer_sync_and_snapshot(monkeypatch):
    """Verify that different phases run at different cadences."""
    calls = []

    # Mock all phase functions to just record their execution
    monkeypatch.setattr(main, "phase_local_crawl", lambda indexer, crawler: calls.append("crawl") or 1)
    monkeypatch.setattr(main, "phase_log_crawl_status", lambda processed, crawler: calls.append("log"))
    monkeypatch.setattr(main, "phase_peer_sync", lambda indexer, peer_urls: calls.append("peer"))
    monkeypatch.setattr(main, "phase_load_previous_snapshot", lambda indexer: calls.append("load") or {"records": []})
    monkeypatch.setattr(main, "phase_diff_and_write", lambda indexer, previous_snapshot: calls.append("diff"))
    monkeypatch.setattr(main, "phase_save_and_archive", lambda indexer: calls.append("save"))
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)

    main.run_loop(
        indexer=object(),
        crawler=object(),
        peer_urls=["http://peer.test/snapshot.json"],
        max_runs=3,
        sleep_seconds=5,
        sync_every=2,      # Every 2 iterations (0, 2)
        snapshot_every=3,  # Every 3 iterations (0)
    )

    # Iteration 0: Everything runs (0 % N is always 0)
    # Iteration 1: Only crawl + log
    # Iteration 2: Crawl + log + peer sync (2 % 2 == 0)
    assert calls == [
        "crawl", "log", "peer", "load", "diff", "save",   # iteration 0
        "crawl", "log",                                    # iteration 1
        "crawl", "log", "peer",                            # iteration 2
    ]

def test_run_loop_rejects_invalid_intervals():
    """Ensure the scheduler doesn't accept zero or negative intervals."""
    with pytest.raises(ValueError):
        main.run_loop(object(), object(), [], max_runs=1, sync_every=0)

    with pytest.raises(ValueError):
        main.run_loop(object(), object(), [], max_runs=1, snapshot_every=0)

def test_run_loop_when_both_intervals_match_preserves_phase_order(monkeypatch):
    """Ensure that when tasks collide, the order remains Sync -> Persist."""
    calls = []

    monkeypatch.setattr(main, "phase_local_crawl", lambda indexer, crawler: calls.append("crawl") or 1)
    monkeypatch.setattr(main, "phase_log_crawl_status", lambda processed, crawler: calls.append("log"))
    monkeypatch.setattr(main, "phase_peer_sync", lambda indexer, peer_urls: calls.append("peer"))
    monkeypatch.setattr(main, "phase_load_previous_snapshot", lambda indexer: calls.append("load") or {"records": []})
    monkeypatch.setattr(main, "phase_diff_and_write", lambda indexer, previous_snapshot: calls.append("diff"))
    monkeypatch.setattr(main, "phase_save_and_archive", lambda indexer: calls.append("save"))
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)

    main.run_loop(
        indexer=object(),
        crawler=object(),
        peer_urls=["http://peer.test/snapshot.json"],
        max_runs=1,
        sync_every=1,
        snapshot_every=1,
    )

    assert calls == ["crawl", "log", "peer", "load", "diff", "save"]