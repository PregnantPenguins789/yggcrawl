import pytest
import time
from crawler import Crawler

def test_backoff_blocks_domain(monkeypatch):
    c = Crawler()
    url = "http://example.com"
    
    # Mock requests.get to always fail
    def mock_get(*args, **kwargs):
        raise Exception("Connection Refused")
    
    import requests
    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr("config.REQUEST_DELAY", 0)

    # First call fails and sets backoff
    with pytest.raises(Exception) as excinfo:
        c.fetch(url)
    assert "Connection Refused" in str(excinfo.value)

    # Second call should immediately hit the Backoff gate (RuntimeError)
    with pytest.raises(RuntimeError) as excinfo:
        c.fetch(url)
    assert "Backoff active" in str(excinfo.value)

def test_backoff_resets_on_success(monkeypatch):
    c = Crawler()
    url = "http://example.com"
    
    # Track calls to simulate a failure followed by a success
    call_count = 0
    
    class MockResponse:
        text = "<html>success</html>"
        def raise_for_status(self): pass

    def mock_get_varying(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Temporary failure")
        return MockResponse()

    import requests
    monkeypatch.setattr(requests, "get", mock_get_varying)
    monkeypatch.setattr("config.REQUEST_DELAY", 0)

    # 1. Fail first
    with pytest.raises(Exception):
        c.fetch(url)
    
    assert "example.com" in c.next_allowed

    # 2. Fast-forward time to bypass backoff for the test
    c.next_allowed["example.com"] = time.time() - 1

    # 3. Succeed second
    c.fetch(url)
    
    # 4. State should be clean
    assert "example.com" not in c.failures
    assert "example.com" not in c.next_allowed