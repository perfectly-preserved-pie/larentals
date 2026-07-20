from pathlib import Path


ANALYTICS_SOURCE = Path(
    "assets/js/clientside_callbacks/plausible_events.js"
).read_text(encoding="utf-8")
POPUP_SOURCE = Path("assets/js/popup.js").read_text(encoding="utf-8")
REPORT_SOURCE = Path("assets/js/report_listing.js").read_text(encoding="utf-8")


def test_all_plausible_product_events_are_instrumented() -> None:
    expected_events = {
        "Filter Changed",
        "Filter Section Opened",
        "Layer Toggled",
        "Basemap Changed",
        "Listing Opened",
        "Listing Link Clicked",
        "School Filter Changed",
        "Report Listing Opened",
        "Report Listing Submitted",
    }

    for event_name in expected_events:
        assert f'"{event_name}"' in ANALYTICS_SOURCE


def test_listing_links_use_delegated_analytics_class() -> None:
    assert POPUP_SOURCE.count('class="plausible-listing-link"') == 2
    assert 'closest(".plausible-listing-link")' in POPUP_SOURCE
    assert "trackListingLinkClicked()" in POPUP_SOURCE


def test_report_submission_tracks_only_after_success() -> None:
    success_branch = REPORT_SOURCE.index("if (response.ok)")
    tracking_call = REPORT_SOURCE.index("trackReportListingSubmitted")
    success_message = REPORT_SOURCE.index("Your report has been submitted")

    assert success_branch < tracking_call < success_message


def test_analytics_payloads_do_not_reference_sensitive_listing_fields() -> None:
    forbidden_property_names = {
        "address",
        "coordinates",
        "latitude",
        "longitude",
        "mls_number",
        "listing_url",
        "search_text",
    }

    for property_name in forbidden_property_names:
        assert property_name not in ANALYTICS_SOURCE


def test_filter_maps_use_only_semantic_categories() -> None:
    assert 'rental_price_slider: "monthly_rent"' in ANALYTICS_SOURCE
    assert 'list_price_slider: "list_price"' in ANALYTICS_SOURCE
    assert '"lease-zip-boundary-store": "location"' in ANALYTICS_SOURCE
    assert '"buy-zip-boundary-store": "location"' in ANALYTICS_SOURCE
    assert 'trackEvent("Filter Changed", { category: category })' in ANALYTICS_SOURCE
