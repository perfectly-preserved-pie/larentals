# Agency subtype recovery

Both listing pipelines now recover missing subtypes across the merged inventory,
including older rows absent from the new source file. The normal incoming-row
detail request and the expiration check both read the same Agency detail endpoint:

```text
https://search-service.idcrealestate.com/api/property/en_US/d4/detail/{board}/{mls_number}
```

Expiration checks now retain the subtype from that existing response. This adds
no HTTP request for a listing already checked through Agency. Known source types
remain authoritative, and a new Unknown does not overwrite a known stored type.

After expiration filtering, a subtype-only pass handles remaining Unknowns whose
lookup is not already complete. This can add requests for listings whose status
was checked through another provider or an older checkpoint without subtype data.
The pass reuses `scraped_subtype` and `subtype_lookup_status` in the market's normal
pipeline checkpoint. Successful no-type outcomes and HTTP 404/410 are reused;
transient failures are retried. A host circuit stops this pass and leaves the
remaining rows pending. It runs no image uploads or geocoding.

The previous flow enriched only incoming source rows before merging old inventory,
so older Unknowns could remain unchanged even when Agency reported a type.

An integration smoke test recovered all four available sampled subtypes using
four expiration requests and zero extra subtype requests. Repeating that pass
with the temporary checkpoints made zero requests. The canonical listing
database was read only; no full backfill was run.

## Live API sample: October 29, 2026

The local database had 2,343 Unknown buy subtypes and 845 Unknown rental subtypes.
Five of those records were sampled:

| Market | MLS | HTTP | PropertyType / PropertyTypeLabel | Canonical subtype |
| --- | --- | --- | --- | --- |
| buy | WS26207673MR | 200 | Single Family | Single Family Residence |
| buy | WS26197146MR | 200 | Condominium | Condominium |
| lease | WS26206810MR | 200 | SINGLE FAMILY | Single Family Residence |
| lease | 26992207 | 200 | CONDOMINIUM | Condominium |
| lease | CV25002817MR | 404 | unavailable | Unknown |

The successful responses were JSON objects with `Content-Type: text/plain`, and
reported home types in `PropertyType` and `PropertyTypeLabel`, rather than a
dedicated subtype key. Trimmed responses are saved in
`tests/fixtures/agency_subtypes_sample.json`. Four recoverable types in this small
sample do not establish coverage across all Unknowns.

The reader also accepts a JSON string containing the detail object. Dedicated
`PropertySubType`, `PropertySubtype`, `SubType`, and `Subtype` keys and explicit
subtype labels under `AddtionalPropertyInfo.Item` (the provider's spelling) take
priority over `PropertyType` and `PropertyTypeLabel`. These alternate subtype
shapes are covered by synthetic tests. Broad markets such as Residential and
architectural styles such as Modern do not establish a home subtype. URLs and
remarks are not used to guess types.

## Standalone subtype-only backfill

The next normal buy/lease pipeline run includes recovery automatically. To update
an existing local database without running either full pipeline:

```bash
.venv/bin/python -m scripts.backfill_listing_subtypes --limit 5
```

Omit `--limit` for a complete pass. The command backs up the database once to
`data/checkpoints/subtypes.before.sqlite` and commits individual outcomes to
`data/checkpoints/subtypes.sqlite`. Re-running replays saved outcomes for still
missing rows. Known subtypes and every unrelated listing column are preserved.
This standalone checkpoint is separate from the normal pipeline checkpoint.
The command does not publish the database. All requests retain the shared pacing,
retry, and circuit behavior.

Focused verification:

```bash
.venv/bin/pytest -q tests/test_listing_subtypes.py tests/test_webscraping_utils.py tests/test_listing_amenities.py tests/test_listing_pipeline_checkpoint.py tests/test_docstring_depth.py
```
