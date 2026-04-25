from sandbox import Sandbox


def test_run_isolated_success():
    def ok(x):
        return x + 1

    result, error = Sandbox.run_isolated(ok, 4)

    assert result == 5
    assert error is None


def test_run_isolated_exception():
    def boom():
        raise ValueError("bad")

    result, error = Sandbox.run_isolated(boom, retries=0)

    assert result is None
    assert "bad" in error


def test_run_isolated_retries(monkeypatch):
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("fail")
        return "ok"

    monkeypatch.setattr("sandbox.time.sleep", lambda _: None)

    result, error = Sandbox.run_isolated(flaky, retries=2)

    assert result == "ok"
    assert error is None
    assert calls["count"] == 3