from functions import webscraping_utils as scraping


class FakeResponse:
    def __init__(self, status_code: int, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def close(self):
        self.closed = True


def test_get_with_backoff_honors_retry_after_and_retries(monkeypatch):
    scraping._next_request_at.clear()
    scraping._cooldown_until.clear()
    clock = [0.0]
    sleeps = []
    responses = [FakeResponse(429, {"Retry-After": "7"}), FakeResponse(200)]

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(scraping.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(scraping.time, "sleep", sleep)
    monkeypatch.setattr(scraping.requests, "get", lambda *args, **kwargs: responses.pop(0))

    response = scraping.get_with_backoff("https://www.bhhscalifornia.com/listing", headers={})

    assert response.status_code == 200
    assert sleeps == [7.0]


def test_get_with_backoff_uses_jittered_backoff_when_retry_after_is_missing(monkeypatch):
    scraping._next_request_at.clear()
    scraping._cooldown_until.clear()
    clock = [0.0]
    sleeps = []
    responses = [FakeResponse(503), FakeResponse(200)]

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(scraping.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(scraping.time, "sleep", sleep)
    monkeypatch.setattr(scraping.random, "uniform", lambda *_: 1.5)
    monkeypatch.setattr(scraping.requests, "get", lambda *args, **kwargs: responses.pop(0))

    response = scraping.get_with_backoff("https://www.bhhscalifornia.com/listing", headers={})

    assert response.status_code == 200
    # The retry delay is followed by the host's five-second request cadence.
    assert sleeps == [1.5, 3.5]
