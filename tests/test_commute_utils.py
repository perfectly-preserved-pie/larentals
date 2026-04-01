from functions import commute_utils


def _build_feature(mls_number: str, lat: float, lon: float) -> dict:
    return {
        "type": "Feature",
        "properties": {"mls_number": mls_number},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def _build_drive_request() -> dict:
    return commute_utils.build_commute_request_data(
        destination="UCLA",
        geocoded={
            "lat": 34.0689,
            "lon": -118.4452,
            "query": "UCLA",
            "bbox": [-118.46, 34.05, -118.43, 34.09],
            "display_name": "UCLA",
        },
        mode="drive",
        minutes=30,
        departure_datetime="2026-04-01T08:00",
        active=True,
        status="Estimated drive area loaded for UCLA.",
        error=None,
    )


def test_verify_exact_commute_matches_partially_verifies_drive_candidates(monkeypatch) -> None:
    monkeypatch.setattr(commute_utils, "VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES", 2)

    def fake_fetch(candidates, destination_lat, destination_lon, mode, departure_datetime):
        assert len(candidates) == 2
        assert destination_lat == 34.0689
        assert destination_lon == -118.4452
        assert mode == "drive"
        assert departure_datetime == "2026-04-01T08:00"
        return {
            "MLS-1": 20 * 60,
            "MLS-2": 45 * 60,
        }

    monkeypatch.setattr(
        commute_utils,
        "fetch_valhalla_route_times_seconds",
        fake_fetch,
    )

    prefiltered_geojson = {
        "type": "FeatureCollection",
        "features": [
            _build_feature("MLS-1", 34.0690, -118.4451),
            _build_feature("MLS-2", 34.0620, -118.4300),
            _build_feature("MLS-3", 34.1800, -118.3000),
        ],
    }

    result = commute_utils.verify_exact_commute_matches(
        prefiltered_geojson=prefiltered_geojson,
        commute_request=_build_drive_request(),
    )

    assert result["provider"] == commute_utils.VALHALLA_SERVICE_LABEL
    assert result["eligible_mls"] == ["MLS-1"]
    assert result["excluded_mls"] == ["MLS-2"]
    assert result["rough_mls"] == ["MLS-3"]
    assert result["attempted_candidates"] == 2
    assert result["checked_candidates"] == 2
    assert result["matched_candidates"] == 1
    assert result["excluded_candidates"] == 1
    assert result["rough_candidates"] == 1
    assert result["partial"] is True
    assert "rough matches remain" in result["status"]


def test_verify_exact_commute_matches_falls_back_to_rough_when_exact_checks_fail(monkeypatch) -> None:
    monkeypatch.setattr(commute_utils, "VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES", 2)
    monkeypatch.setattr(
        commute_utils,
        "fetch_valhalla_route_times_seconds",
        lambda *args, **kwargs: {"MLS-1": None, "MLS-2": None},
    )

    prefiltered_geojson = {
        "type": "FeatureCollection",
        "features": [
            _build_feature("MLS-1", 34.0690, -118.4451),
            _build_feature("MLS-2", 34.0620, -118.4300),
            _build_feature("MLS-3", 34.1800, -118.3000),
        ],
    }

    result = commute_utils.verify_exact_commute_matches(
        prefiltered_geojson=prefiltered_geojson,
        commute_request=_build_drive_request(),
    )

    assert result["error"] == "Exact commute estimates unavailable right now. Showing rough matches only."
    assert result["checked_candidates"] == 0
    assert result["failed_candidates"] == 2
    assert result["rough_mls"] == ["MLS-1", "MLS-2", "MLS-3"]
