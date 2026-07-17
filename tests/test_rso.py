import gzip

import orjson

from functions import rso


def test_decode_powerbi_rows_expands_dictionaries_and_repeated_values() -> None:
    dataset = {
        "ValueDicts": {"D0": ["123 MAIN ST"], "D1": ["LOS ANGELES"], "D2": ["90001"], "D3": ["2-4 units"]},
        "PH": [
            {
                "DM0": [
                    {
                        "S": [
                            {"N": "G0", "T": 4},
                            {"N": "G1", "T": 4},
                            {"N": "G2", "T": 1, "DN": "D0"},
                            {"N": "G3", "T": 1, "DN": "D1"},
                            {"N": "G4", "T": 1, "DN": "D2"},
                            {"N": "G5", "T": 4},
                            {"N": "G6", "T": 1, "DN": "D3"},
                        ],
                        "C": [1234567890, 2026, 0, 0, 0, 2, 0],
                    },
                    {"C": [1234567891], "R": 126},
                ]
            }
        ],
    }

    rows = rso._decode_powerbi_rows(dataset)

    assert rows == [
        {
            "apn": "1234567890",
            "rso_year": 2026,
            "address": "123 MAIN ST",
            "city": "LOS ANGELES",
            "zip": "90001",
            "rso_units": 2,
            "unit_range": "2-4 units",
        },
        {
            "apn": "1234567891",
            "rso_year": 2026,
            "address": "123 MAIN ST",
            "city": "LOS ANGELES",
            "zip": "90001",
            "rso_units": 2,
            "unit_range": "2-4 units",
        },
    ]


def test_lookup_reports_all_or_some_coverage_conservatively(tmp_path) -> None:
    artifact = tmp_path / "rso.json.gz"
    payload = {
        "records": [
            {"apn": "1", "address": "123 MAIN STREET", "rso_units": 2, "unit_range": "2 units", "rso_year": 2026},
            {"apn": "2", "address": "456 MAIN STREET", "rso_units": 2, "unit_range": "2-4 units", "rso_year": 2026},
        ]
    }
    with gzip.open(artifact, "wb") as artifact_file:
        artifact_file.write(orjson.dumps(payload))

    rso._load_lookup.cache_clear()
    all_covered = rso.lookup_rso_property_for_listing("123 Main St #4", artifact)
    mixed = rso.lookup_rso_property_for_listing("456 Main St Apt B", artifact)
    missing = rso.lookup_rso_property_for_listing("789 Main St", artifact)

    assert all_covered["coverage"] == "all"
    assert mixed["coverage"] == "some"
    assert missing == rso._empty_result(data_available=True)
