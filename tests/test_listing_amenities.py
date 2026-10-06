"""Cover source extraction, checkpoint reuse, and rental UI data boundaries."""

import json
from pathlib import Path
import sqlite3
from typing import Any
from types import SimpleNamespace

from flask import Flask
import pandas as pd
import pytest

from api.listings import LEASE_LISTING_DETAIL_SQL, BUY_LISTING_DETAIL_SQL, register_listing_routes
from functions.dataframe_utils import update_dataframe_with_listing_data
from functions.listing_pipeline_checkpoint import ListingCheckpointStore
from functions.webscraping_utils import extract_listing_amenities, extract_bhhs_amenities, fetch_the_agency_data, BeautifulSoup
from pages.component_factories import build_amenity_filters


def test_live_agency_samples() -> None:
    """Keep the observed provider labels as an offline regression fixture.

    Equipment may name dishwasher even when the separate Appliances list omits it.

    Returns:
        None.
    """
    samples = json.loads((Path(__file__).parent / "fixtures/agency_amenities_sample.json").read_text())
    for row in samples:
        assert extract_listing_amenities(row['AddtionalPropertyInfo']['Item']) == row['expected']


@pytest.mark.parametrize("fields, expected", [
    ([], {"has_ac": None, "has_dishwasher": None}),
    ([{"Label": "Cooling", "Value": "None"}, {"Label": "Appliances", "Value": "No appliances"}], {"has_ac": "No", "has_dishwasher": "No"}),
    ([{"Label": "Cooling", "Value": "Ceiling Fan"}, {"Label": "Equipment", "Value": "Refrigerator"}], {"has_ac": None, "has_dishwasher": None}),
    ([{"Label": "Cooling", "Value": "Wall/Window Unit(s)"}, {"Label": "Equipment", "Value": "No dishwasher"}], {"has_ac": "Yes", "has_dishwasher": "No"}),
    ([{"Label": "Cooling", "Value": "No central air conditioning"}], {"has_ac": None, "has_dishwasher": None}),
    ([{"Label": "Cooling", "Value": None}, {"Label": "Remarks", "Value": "AC and dishwasher included"}], {"has_ac": None, "has_dishwasher": None}),
    ([{"Label": "Cooling", "Value": "Ductless"}, {"Label": "Dishwasher", "Value": "Yes"}], {"has_ac": "Yes", "has_dishwasher": "Yes"}),
])
def test_amenity_unknown_and_negative_boundaries(fields: list[dict[str, Any]], expected: dict[str, str | None]) -> None:
    """Treat omissions and non-AC cooling separately from reported absence.

    Free text must not confirm features that the structured provider data lacks.

    Args:
        fields: Labeled provider details exercising missing and negative cases.
        expected: Expected AC and dishwasher statuses.

    Returns:
        None.
    """
    assert extract_listing_amenities(fields) == expected


def test_bhhs_uses_labeled_fields() -> None:
    """Accept dedicated detail labels without reading promotional descriptions.

    A missing appliances label leaves dishwasher unknown even if prose mentions it.

    Returns:
        None.
    """
    soup = BeautifulSoup('<dl><dt>Cooling:</dt><dd>Central</dd><dt>Equipment</dt><dd>Dishwasher</dd></dl>', 'html.parser')
    assert extract_bhhs_amenities(soup) == {"has_ac": "Yes", "has_dishwasher": "Yes"}
    assert extract_bhhs_amenities(BeautifulSoup('<p>Central AC and dishwasher</p>', 'html.parser')) == {"has_ac": None, "has_dishwasher": None}


def test_amenity_checkpoint_upgrade_and_resume(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Refresh legacy checkpoints once and reuse known or unknown amenities.

    Existing photos remain reusable when only the amenity schema is upgraded.

    Args:
        monkeypatch: Fixture replacing provider and image services.
        tmp_path: Directory for an isolated checkpoint database.

    Returns:
        None.
    """
    calls = []
    store = ListingCheckpointStore(tmp_path / 'checkpoint.db', listing_type='lease')
    source = pd.DataFrame([{'mls_number': 'MLS-1'}])
    monkeypatch.setattr('functions.dataframe_utils.fetch_the_agency_data', lambda *args, **kwargs: calls.append(args) or (pd.Timestamp('2026-10-01'), 'https://example.test/listing', 'https://example.test/photo', None))
    monkeypatch.setattr('functions.dataframe_utils.imagekit_transform', lambda *args, **kwargs: 'https://example.test/image')
    update_dataframe_with_listing_data(source.copy(), object(), checkpoint_store=store)
    with sqlite3.connect(store.path) as conn:
        conn.execute('UPDATE listing_checkpoint SET amenity_lookup_status = NULL')
    monkeypatch.setattr('functions.dataframe_utils.fetch_the_agency_data', lambda *args, **kwargs: calls.append(args) or (pd.Timestamp('2026-10-01'), 'https://example.test/listing', 'https://example.test/photo', None, {'has_ac': 'Yes', 'has_dishwasher': None}))
    monkeypatch.setattr('functions.dataframe_utils.imagekit_transform', lambda *args, **kwargs: pytest.fail('cached photo must not upload again'))
    for _ in range(2):
        result = update_dataframe_with_listing_data(source.copy(), object(), checkpoint_store=store)
        assert result.loc[0, 'has_ac'] == 'Yes'
        assert pd.isna(result.loc[0, 'has_dishwasher'])
    assert len(calls) == 2


@pytest.mark.parametrize('with_amenities', [False, True])
@pytest.mark.parametrize('listing_type', ['lease', 'buy'])
def test_listing_api_supports_legacy_and_enriched_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_amenities: bool, listing_type: str) -> None:
    """Return safe popup statuses before and after the table schema upgrade.

    A deployment can ship UI changes before the next scheduled pipeline run.

    Args:
        tmp_path: Directory containing the isolated listing database.
        monkeypatch: Fixture replacing unrelated property lookups.
        with_amenities: Whether the fixture has the new amenity columns.
        listing_type: Market whose table and popup API are being checked.

    Returns:
        None.
    """
    query = LEASE_LISTING_DETAIL_SQL if listing_type == 'lease' else BUY_LISTING_DETAIL_SQL
    selection = query.split('SELECT')[1].split('FROM')[0]
    selection = selection.replace("COALESCE(laundry_category, 'Unknown') AS laundry", "laundry_category")
    columns = [column.strip() for column in selection.split(',')]
    schema = f"CREATE TABLE {listing_type} (" + ", ".join(f"{column} TEXT" for column in columns) + ")"
    db = tmp_path / 'listings.db'
    with sqlite3.connect(db) as conn:
        conn.execute(schema)
        if with_amenities:
            conn.execute(f'ALTER TABLE {listing_type} ADD COLUMN has_ac TEXT')
            conn.execute(f'ALTER TABLE {listing_type} ADD COLUMN has_dishwasher TEXT')
            conn.execute(f"INSERT INTO {listing_type} (mls_number, has_ac, has_dishwasher) VALUES ('MLS-1', 'Yes', 'No')")
        else:
            conn.execute(f"INSERT INTO {listing_type} (mls_number) VALUES ('MLS-1')")
    monkeypatch.setattr('api.listings.build_lahd_listing_summary', lambda payload: {})
    monkeypatch.setattr('api.listings.build_rso_listing_summary', lambda payload: {})
    server = Flask(__name__)
    register_listing_routes(server, str(db))
    response = server.test_client().get(f'/api/{listing_type}/listing-details/MLS-1')
    assert response.status_code == 200
    assert response.json['has_ac'] == ('Yes' if with_amenities else None)
    assert response.json['has_dishwasher'] == ('No' if with_amenities else None)


def test_amenity_controls_start_with_any_and_counts() -> None:
    """Expose reported counts while keeping all listings visible by default.

    The shared checkbox group uses a stable ID captured by the responsive filter state.

    Returns:
        None.
    """
    listings = pd.DataFrame({'has_ac': ['Yes', 'No', None], 'has_dishwasher': [None, 'Yes', None]})
    group = build_amenity_filters(listings)
    assert group.id == 'required_amenities'
    assert group.value == []
    assert [child.value for child in group.children.children] == ['has_ac', 'has_dishwasher']
    assert group.children.children[1].label == 'Dishwasher (1 reported)'


@pytest.mark.parametrize("details, expected", [
    ({"Item": [{"Label": "Cooling", "Value": "Central"}, {"Label": "Equipment", "Value": "Dishwasher"}]}, {"has_ac": "Yes", "has_dishwasher": "Yes"}),
    ({"Item": {"Label": "Cooling", "Value": "None"}}, {"has_ac": "No", "has_dishwasher": None}),
    ({"Item": None}, {"has_ac": None, "has_dishwasher": None}),
    (None, {"has_ac": None, "has_dishwasher": None}),
])
def test_agency_detail_items_flow_into_scrape_tuple(monkeypatch: pytest.MonkeyPatch, details: Any, expected: dict[str, str | None]) -> None:
    """Read the provider's nested detail container with singleton and null cases.

    Missing feature containers must not discard otherwise usable listing details.

    Args:
        monkeypatch: Fixture replacing the provider HTTP request.
        details: Provider detail container, including missing and singleton cases.
        expected: Expected AC and dishwasher statuses in the scrape tuple.

    Returns:
        None.
    """
    payload = {"DetailUrl": "/listing", "AddtionalPropertyInfo": details}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr("functions.webscraping_utils.get_with_backoff", lambda *args, **kwargs: response)
    listing = fetch_the_agency_data("MLS-1", 0, 1)
    assert listing[1] == "https://www.theagencyre.com/listing"
    assert listing[4] == expected
