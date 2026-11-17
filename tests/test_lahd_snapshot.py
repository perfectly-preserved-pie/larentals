"""Verify complete downloads, revision reuse, and local-only property reads."""

import gzip
from pathlib import Path
from types import SimpleNamespace

import orjson
import pytest

from functions import lahd, lahd_snapshot as snapshot


def test_complete_snapshot_and_unchanged_revisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Download every page once and skip raw data when source revisions match.

    A small page size catches builders that silently retain only the first page.
    Property reads then normalize rows without issuing any HTTP requests.

    Args:
        tmp_path: Isolated snapshot destination.
        monkeypatch: Fixture replacing Socrata responses and local snapshot reads.

    Returns:
        None.
    """
    rows = {
        "eagk-wq48": [
            {"apn": "123-45", "case_filed_date": "2024-01-01", "casetype": "Older"},
            {"apn": "12345", "case_filed_date": "2025-01-01", "casetype": "Newest"},
            {"apn": "67890", "case_filed_date": "2023-01-01"},
        ],
        "cr8f-uc4j": [{"apn": "12345", "violationtype": "WIRING", "violations_cited": "2025-01-01"}],
    }
    calls = []

    def get(url, params=None, **kwargs):
        """Return stable metadata and paginated raw rows from the fake source.

        Args:
            url: Requested Socrata URL.
            params: Optional query fields and pagination.
            kwargs: Unused HTTP options accepted by the stub.

        Returns:
            Minimal response implementing the downloader's requests interface.
        """
        calls.append((url, params))
        dataset = url.rsplit('/', 1)[-1].removesuffix('.json')
        if '/api/views/' in url:
            payload = {"rowsUpdatedAt": 1234}
        elif '$select' in params:
            payload = [{"count": str(len(rows[dataset]))}]
        else:
            start = params['$offset']
            payload = rows[dataset][start:start + params['$limit']]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr(snapshot.requests, 'get', get)
    monkeypatch.setattr(snapshot, 'PAGE_SIZE', 2)
    output = tmp_path / 'lahd.json.gz'
    assert snapshot.refresh_records_snapshot(output)
    with gzip.open(output, 'rb') as source:
        downloaded = orjson.loads(source.read())
    assert len(downloaded['cases']) == 3
    assert len(downloaded['violations']) == 1
    before = output.read_bytes()
    calls.clear()
    assert not snapshot.refresh_records_snapshot(output)
    assert output.read_bytes() == before
    assert len(calls) == 2
    assert all('/api/views/' in url for url, _ in calls)

    local = snapshot.read_records_snapshot(output)
    monkeypatch.setattr(lahd, 'read_records_snapshot', lambda: local)
    monkeypatch.setattr(snapshot.requests, 'get', lambda *a, **k: pytest.fail('visitor reads must not use HTTP'))
    details = lahd.load_lahd_property_record_details('123-45', row_limit=1)
    assert details['cases'][0]['case_type'] == 'Newest'
    assert details['truncated']['cases'] is True
    assert details['detail_status']['source_mode'] == 'local_snapshot'
    assert lahd.load_lahd_property_record_details('99999')['cases'] == []


@pytest.mark.parametrize('failure', ['short_page', 'revision_changed'])
def test_incomplete_refresh_retains_previous_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    """Never publish a partial dataset or mixed source revisions.

    A failed quarterly check must leave the previous Git artifact usable.

    Args:
        tmp_path: Isolated artifact destination.
        monkeypatch: Fixture simulating a source edit or truncated download.
        failure: Source fault injected during the download.

    Returns:
        None.
    """
    output = tmp_path / 'lahd.json.gz'
    with gzip.open(output, 'wb') as destination:
        destination.write(orjson.dumps({"version": 1, "sources": {}}))
    before = output.read_bytes()
    revisions = {dataset: 0 for dataset in snapshot.DATASETS.values()}

    def metadata(dataset):
        """Advance the source revision only when simulating a mid-download edit.

        Args:
            dataset: Requested Socrata identifier.

        Returns:
            Metadata used by the builder's revision comparison.
        """
        revisions[dataset] += 1
        revision = revisions[dataset] if failure == 'revision_changed' else 1
        return {"dataset": dataset, "rows_updated_at": revision}

    def get(url, params, **kwargs):
        """Claim two rows but truncate the second page for the short-page fault.

        Args:
            url: Requested source URL.
            params: Count or raw pagination query.
            kwargs: Unused HTTP options.

        Returns:
            Fake source response.
        """
        payload = [{"count": "2"}] if '$select' in params else ([{"apn": "12345"}] if failure == 'short_page' and params['$offset'] == 0 else [])
        if failure == 'revision_changed' and '$select' not in params:
            payload = [{"apn": "12345"}, {"apn": "67890"}]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr(snapshot, 'source_metadata', metadata)
    monkeypatch.setattr(snapshot.requests, 'get', get)
    with pytest.raises(ValueError):
        snapshot.refresh_records_snapshot(output)
    assert output.read_bytes() == before
