import crawler


def test_fetch_returns_content(monkeypatch):
    class FakeResponse:
        def __init__(self):
            self.text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(crawler.requests, "get", fake_get)

    c = crawler.Crawler()
    content = c.fetch("http://example.com")

    assert content == "<html>ok</html>"


def test_fetch_applies_rate_limit(monkeypatch):
    sleep_calls = []

    class FakeResponse:
        def __init__(self):
            self.text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    times = iter([100.0, 100.2, 100.2, 101.3])

    def fake_time():
        return next(times)

    def fake_sleep(seconds):
        sleep_calls.append(seconds)

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(crawler.time, "time", fake_time)
    monkeypatch.setattr(crawler.time, "sleep", fake_sleep)
    monkeypatch.setattr(crawler.requests, "get", fake_get)

    c = crawler.Crawler()
    c.fetch("http://example.com")
    c.fetch("http://example.com")

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0


def test_fetch_sends_user_agent(monkeypatch):
    captured = {}

    class FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    def fake_get(url, timeout, headers):
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(crawler.requests, "get", fake_get)

    c = crawler.Crawler()
    c.fetch("http://example.com")

    assert "User-Agent" in captured["headers"]
    assert "YggCrawl" in captured["headers"]["User-Agent"]


def test_fetch_raises_on_http_error(monkeypatch):
    class BoomResponse:
        text = ""

        def raise_for_status(self):
            raise RuntimeError("http fail")

    def fake_get(*args, **kwargs):
        return BoomResponse()

    monkeypatch.setattr(crawler.requests, "get", fake_get)

    c = crawler.Crawler()

    try:
        c.fetch("http://example.com")
        assert False, "expected exception"
    except RuntimeError as e:
        assert "http fail" in str(e)