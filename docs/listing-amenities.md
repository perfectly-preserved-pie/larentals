# AC and dishwasher filters

Both rental and for-sale pages offer an **Amenities** section after Bathrooms,
using a shared Mantine checkbox group labeled **Must have**. Users can require
Air conditioning, Dishwasher, or both. Neither checked applies no restriction;
both checked require both amenities to be reported present. Counts describe the
whole page inventory, like the existing home-type filters. On phones, selections
remain drafts until Apply, and Clear all unchecks both. Amenities starts collapsed on desktop and phones. The lease Amenities section also contains the
existing Laundry dropdown and unknown-data switch, separated by a labeled
divider. Laundry selections count as part of the Amenities group. Popups show
Yes/No (reported) or Not reported.

The listing pipeline reads `AddtionalPropertyInfo.Item` (the provider's actual
spelling) from the existing Agency detail API request. Dedicated `Cooling`,
`Appliances`, `Equipment`, and `Dishwasher` labels are interpreted. `Equipment`
is essential: one sampled listing has an Appliances list without dishwasher but
an Equipment list that includes it. Free-form remarks are excluded because they
can describe other units. Omitted dishwasher entries and generic `Appliances:
None` stay unknown; explicit `Cooling: None` denotes no cooling. Unknown is not
proof that an amenity is absent.

Nullable `has_ac` and `has_dishwasher` columns contain `Yes`, `No`, or SQL NULL.
These fields flow through the normal pipeline table publication. Existing
checkpoints are refreshed once for the new amenity lookup; subsequent resumes
reuse both known and unknown outcomes. Previously uploaded images remain reusable.
The existing BHHS fallback request can supply dedicated HTML feature labels, but
missing amenities alone do not trigger another BHHS request.

The UI and popup API also support older databases without the new columns. Until
the next listing pipeline refresh, those records appear as Not reported. No bulk
refresh or production deployment was performed for this change.

## Live sample on October 6, 2026

Five recent local rental rows and four for-sale rows were requested from the public Agency API. Eight
returned HTTP 200; `AR26213712MR` returned HTTP 404. The successful responses are
preserved as trimmed source fixtures in
`tests/fixtures/agency_amenities_sample.json`.

| MLS | Cooling | Dishwasher evidence | Status |
| --- | --- | --- | --- |
| 26995393 | Air Conditioning | Equipment includes Dishwasher | AC Yes; dishwasher Yes |
| 26995421 | Central | Equipment includes Dishwasher | AC Yes; dishwasher Yes |
| 26995453 | Air Conditioning | Appliances says None | AC Yes; dishwasher Not reported |
| 26995521 (lease) | Central | Equipment includes Dishwasher | AC Yes; dishwasher Yes |
| 26836705 (buy) | Air Conditioning | Equipment includes Dishwasher | AC Yes; dishwasher Yes |
| 26993535 (buy) | Wall Unit(s) | Equipment includes Dishwasher | AC Yes; dishwasher Yes |
| 26994977 (buy) | Air Conditioning, Central | Equipment includes Dishwasher | AC Yes; dishwasher Yes |
| 26995263 (buy) | Air Conditioning, Central | Equipment includes Dishwasher | AC Yes; dishwasher Yes |

The BHHS search page for `26995393` timed out after 25 seconds from this environment.
Its labeled HTML fallback is covered by synthetic tests; live BHHS availability
and markup could not be confirmed. This is a small feasibility sample, not an
estimate of coverage across the inventory.

Run the focused backend checks with:

```bash
.venv/bin/pytest -q tests/test_listing_amenities.py tests/test_webscraping_utils.py tests/test_listing_pipeline_checkpoint.py tests/test_component_base.py tests/test_component_smoke.py tests/test_docstring_depth.py
```

Browser checks live in `tests/e2e/listing_amenities.spec.js`.
