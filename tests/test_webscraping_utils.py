from functions import webscraping_utils as scraping
import pytest
import requests
from urllib.parse import parse_qs, urlparse


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        headers: dict[str, str] | None = None,
        json_data: object = None,
    ) -> None:
        """Initialize the instance.

        Args:
            status_code: HTTP status code exposed by the fake response.
            headers: HTTP headers included with the request.
            json_data: Decoded JSON payload returned by ``json``.

        Returns:
            None.
        """
        self.status_code = status_code
        self.headers = headers or {}
        self.json_data = json_data
        self.closed = False

    def close(self) -> None:
        """Handle close.

        Returns:
            None.
        """
        self.closed = True

    def json(self) -> object:
        """Return the configured JSON response payload.

        Returns:
            The configured decoded response body.
        """
        return self.json_data

    def raise_for_status(self) -> None:
        """Raise the same exception family as ``requests.Response``.

        Returns:
            None.

        Raises:
            requests.HTTPError: If the fake status is an HTTP error.
        """
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=self,
            )


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


def test_agency_active_index_reports_active_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An active Agency record should finish the lookup without a second call.

    Args:
        monkeypatch: Pytest fixture used to replace the HTTP dependency.

    Returns:
        None.
    """
    urls: list[str] = []

    def fake_get(url: str, *, headers: dict[str, str]) -> FakeResponse:
        """Return one active Agency response.

        Args:
            url: Requested Agency endpoint.
            headers: HTTP headers included with the request.

        Returns:
            A fake active listing response.
        """
        urls.append(url)
        return FakeResponse(200, json_data={"Status": "Active"})

    monkeypatch.setattr(scraping, "get_with_backoff", fake_get)

    result = scraping.check_expired_listing_theagency(
        "https://www.theagencyre.com/condominium/clr/MLS-1/address",
        "MLS-1",
    )

    assert result is False
    assert urls == [
        "https://search-service.idcrealestate.com/api/property/en_US/d4/detail/clr/MLS-1"
    ]


def test_agency_off_market_index_recognizes_expired_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The off-market payload uses Status/IsOffMarket rather than IsSold.

    Args:
        monkeypatch: Pytest fixture used to replace the HTTP dependency.

    Returns:
        None.
    """
    responses = [
        FakeResponse(404),
        FakeResponse(
            200,
            json_data={"Status": "Expired", "IsOffMarket": True},
        ),
    ]

    monkeypatch.setattr(
        scraping,
        "get_with_backoff",
        lambda *args, **kwargs: responses.pop(0),
    )

    assert (
        scraping.check_expired_listing_theagency("", "21-773252") is True
    )


def test_agency_missing_from_both_indexes_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two missing records must not be treated as proof of an active listing.

    Args:
        monkeypatch: Pytest fixture used to replace the HTTP dependency.

    Returns:
        None.
    """
    responses = [FakeResponse(404), FakeResponse(404)]
    monkeypatch.setattr(
        scraping,
        "get_with_backoff",
        lambda *args, **kwargs: responses.pop(0),
    )

    assert scraping.check_expired_listing_theagency("", "UNKNOWN") is None


def test_rentcast_matches_exact_mls_across_active_and_inactive_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relisted address must not hide the inactive status of the old MLS ID.

    Args:
        monkeypatch: Pytest fixture used to replace the HTTP dependency.

    Returns:
        None.
    """
    urls: list[str] = []
    responses = [
        FakeResponse(200, json_data=[{"mlsNumber": "NEW-MLS"}]),
        FakeResponse(200, json_data=[{"mlsNumber": "OLD-MLS"}]),
    ]

    def fake_get(url: str, *, headers: dict[str, str]) -> FakeResponse:
        """Return each configured RentCast response in order.

        Args:
            url: Requested RentCast endpoint and query string.
            headers: HTTP headers included with the request.

        Returns:
            The next fake listing response.
        """
        urls.append(url)
        assert headers["X-Api-Key"] == "test-key"
        return responses.pop(0)

    monkeypatch.setattr(scraping, "get_with_backoff", fake_get)

    result = scraping.check_expired_listing_rentcast(
        "100 Main St, Los Angeles 90001",
        "OLD-MLS",
        "lease",
        api_key="test-key",
    )

    assert result is True
    queries = [parse_qs(urlparse(url).query) for url in urls]
    assert [query["status"] for query in queries] == [["Active"], ["Inactive"]]
    assert all(
        query["address"] == ["100 Main St, Los Angeles, CA 90001"]
        for query in queries
    )


def test_rentcast_missing_exact_mls_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coverage gaps or another listing at the address are not inactive proof.

    Args:
        monkeypatch: Pytest fixture used to replace the HTTP dependency.

    Returns:
        None.
    """
    monkeypatch.setattr(
        scraping,
        "get_with_backoff",
        lambda *args, **kwargs: FakeResponse(
            200,
            json_data=[{"mlsNumber": "DIFFERENT-MLS"}],
        ),
    )

    assert (
        scraping.check_expired_listing_rentcast(
            "100 Main St, Los Angeles 90001",
            "MISSING-MLS",
            "buy",
            api_key="test-key",
        )
        is None
    )
