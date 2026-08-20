from functions import webscraping_utils as scraping
import pytest
import requests


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize the instance.

        Args:
            status_code: HTTP status code exposed by the fake response.
            headers: HTTP headers included with the request.

        Returns:
            None.
        """
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def close(self) -> None:
        """Handle close.

        Returns:
            None.
        """
        self.closed = True


def test_get_with_backoff_honors_retry_after_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that get with backoff honors retry after and retries.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    scraping._next_request_at.clear()
    scraping._cooldown_until.clear()
    scraping._transport_failures.clear()
    scraping._circuit_open_until.clear()
    clock = [0.0]
    sleeps = []
    responses = [FakeResponse(429, {"Retry-After": "7"}), FakeResponse(200)]

    def sleep(seconds: float) -> None:
        """Handle sleep.

        Args:
            seconds: Simulated sleep duration in seconds.

        Returns:
            None.
        """
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(scraping.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(scraping.time, "sleep", sleep)
    monkeypatch.setattr(scraping.requests, "get", lambda *args, **kwargs: responses.pop(0))

    response = scraping.get_with_backoff("https://www.bhhscalifornia.com/listing", headers={})

    assert response.status_code == 200
    assert sleeps == [7.0]


def test_get_with_backoff_uses_jittered_backoff_when_retry_after_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that get with backoff uses jittered backoff when retry after is missing.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    scraping._next_request_at.clear()
    scraping._cooldown_until.clear()
    scraping._transport_failures.clear()
    scraping._circuit_open_until.clear()
    clock = [0.0]
    sleeps = []
    responses = [FakeResponse(503), FakeResponse(200)]

    def sleep(seconds: float) -> None:
        """Handle sleep.

        Args:
            seconds: Simulated sleep duration in seconds.

        Returns:
            None.
        """
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


def test_get_with_backoff_opens_circuit_after_repeated_connection_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that get with backoff opens circuit after repeated connection failures.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    scraping._next_request_at.clear()
    scraping._cooldown_until.clear()
    scraping._transport_failures.clear()
    scraping._circuit_open_until.clear()
    clock = [0.0]
    request_count = [0]

    def sleep(seconds: float) -> None:
        """Handle sleep.

        Args:
            seconds: Simulated sleep duration in seconds.

        Returns:
            None.
        """
        clock[0] += seconds

    def fail_request(*args: object, **kwargs: object) -> None:
        """Handle fail request.

        Args:
            *args: Additional positional arguments forwarded to the dependency.
            **kwargs: Additional keyword arguments forwarded to the dependency.

        Returns:
            None.

        Raises:
            requests.ConnectionError: If the operation cannot be completed.
        """
        request_count[0] += 1
        raise requests.ConnectionError(ConnectionResetError(104, "Connection reset by peer"))

    monkeypatch.setattr(scraping.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(scraping.time, "sleep", sleep)
    monkeypatch.setattr(scraping.random, "uniform", lambda *_: 1.0)
    monkeypatch.setattr(scraping.requests, "get", fail_request)

    with pytest.raises(scraping.HostCircuitOpen):
        scraping.get_with_backoff("https://www.bhhscalifornia.com/listing", headers={})

    assert request_count[0] == scraping.TRANSPORT_FAILURE_THRESHOLD

    # Other listings fail fast while the host is paused rather than repeating
    # the same network retries.
    with pytest.raises(scraping.HostCircuitOpen):
        scraping.get_with_backoff("https://www.bhhscalifornia.com/another", headers={})
    assert request_count[0] == scraping.TRANSPORT_FAILURE_THRESHOLD


def test_transport_failure_count_is_exposed_before_circuit_opens() -> None:
    """Verify that transport failure count is exposed before circuit opens.

    Returns:
        None.
    """
    scraping._transport_failures.clear()
    scraping._circuit_open_until.clear()
    host = "search-service.idcrealestate.com"
    error = requests.Timeout("read timed out")

    failures = scraping._record_transport_failure(host, error)

    assert failures == 1
    assert scraping._transport_failures[host] == 1
    assert host not in scraping._circuit_open_until


def test_get_with_backoff_recovers_after_circuit_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that get with backoff recovers after circuit cooldown.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    scraping._next_request_at.clear()
    scraping._cooldown_until.clear()
    scraping._transport_failures.clear()
    scraping._circuit_open_until.clear()
    clock = [scraping.HOST_CIRCUIT_OPEN_SECONDS + 1.0]
    host = "www.bhhscalifornia.com"
    scraping._transport_failures[host] = scraping.TRANSPORT_FAILURE_THRESHOLD
    scraping._circuit_open_until[host] = scraping.HOST_CIRCUIT_OPEN_SECONDS

    monkeypatch.setattr(scraping.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(scraping.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        scraping.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(200),
    )

    response = scraping.get_with_backoff(
        "https://www.bhhscalifornia.com/listing",
        headers={},
    )

    assert response.status_code == 200
    assert host not in scraping._transport_failures
    assert host not in scraping._circuit_open_until


def test_host_circuits_are_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that host circuits are isolated.

    Args:
        monkeypatch: Pytest fixture used to replace dependencies during the test.

    Returns:
        None.
    """
    scraping._next_request_at.clear()
    scraping._cooldown_until.clear()
    scraping._transport_failures.clear()
    scraping._circuit_open_until.clear()
    agency_host = "search-service.idcrealestate.com"
    scraping._circuit_open_until[agency_host] = 60.0
    request_count = [0]

    def successful_request(*args: object, **kwargs: object) -> FakeResponse:
        """Handle successful request.

        Args:
            *args: Additional positional arguments forwarded to the dependency.
            **kwargs: Additional keyword arguments forwarded to the dependency.

        Returns:
            An HTTP response containing the successful request.
        """
        request_count[0] += 1
        return FakeResponse(200)

    monkeypatch.setattr(scraping.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(scraping.requests, "get", successful_request)

    with pytest.raises(scraping.HostCircuitOpen):
        scraping.get_with_backoff(
            f"https://{agency_host}/api/property",
            headers={},
        )

    response = scraping.get_with_backoff(
        "https://www.bhhscalifornia.com/listing",
        headers={},
    )

    assert response.status_code == 200
    assert request_count[0] == 1
