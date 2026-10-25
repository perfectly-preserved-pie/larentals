# Property records and mapped hazards

Both listing popups show an independently loaded property summary and a
**View property records** button. The responsive drawer starts with hazards,
zoning, and permits for buyers, and housing protections for renters. Existing
LAHD issue records and the rental RSO inventory remain available in the popup.

## Official sources

- **ZIMAS:** the public application's `zm4WS/GetProjectData` PIN profile and
  ArcGIS `zim4s.pin_address` address table. Useful fields include full zoning
  strings, restrictions/overlays, parcel hazard flags, housing notes, and
  property planning cases. Both original and Chapter 1A zoning strings are
  preserved. Private assessor/ownership fields are excluded.
- **CAL FIRE:** official hosted `FHSALRA25_v1_All` and `FHSZSRA_23_3` feature
  services. Both LRA and SRA are queried. LRA is labeled as the 2025 state
  recommendation, not a determination of local adoption. A mapped
  `NonWildland` designation is displayed as “Non-wildland (mapped)”.
- **FEMA:** current National Flood Hazard Layer, layer 28. Flood zone,
  subtype, and Special Flood Hazard Area status are preserved. In particular,
  zone X does not lose its distinction between minimal hazard and the mapped
  0.2% annual-chance flood hazard.
- **LA City building permits:** `pi9x-tg5x`, issued building permits from 2020
  to present. The drawer shows the latest 25 permits and identifies when more
  are available. Work descriptions, issuance dates, recorded statuses, status
  dates, and source refresh dates are retained. Electrical, mechanical, older,
  pending, and inspection records are linked through LADBS rather than inferred
  from this feed.

Sources and their applicability were verified on October 25, 2026. ZIMAS's
current housing profile includes JCO information; AB 1482 information is shown
when the source supplies it, rather than inferred from year built or zoning.

## Identity and coverage

The endpoint is `/api/<buy|lease>/property-context/<mls_number>`. It reads the
address, ZIP, city, and coordinates from the stored listing; client-supplied
addresses or locations cannot override them.

ZIMAS matching strips unit fragments, normalizes street suffixes, and requires
the same house number, route, supplied direction, and ZIP when available. A
directionless address must resolve to exactly one PIN. The returned profile's
address and PIN are checked again. Neither nearby coordinates nor a larger
issue count can select a parcel. Exact address-list queries are intentional:
ZIMAS's edge firewall rejects some otherwise valid compound ArcGIS queries.

Permit queries use the verified city PIN, not a guessed condo APN. These are
property-level records and may include work on other units. Planning cases
are likewise property records, not predictions of nearby construction.

Statewide fire and federal flood queries use the listing point. They do not
evaluate the whole parcel. ZIMAS hazard flags, including its older very-high
fire flag, remain separately attributed rather than overriding the CAL FIRE
designation. Seismic flags describe mapped ground hazards, not a building's
earthquake performance; the drawer links to CGS for additional locations.

City records distinguish unavailable sources, outside-city coverage, and an
unmatched address. Empty hazard intersections never become “low risk” or “no
hazard”. An empty permit feed means no matching records in that dataset, not
that a property has no permits or that work was unpermitted.

## Loading and cache

Agency requests never run in the listing-detail route or at page startup.
The browser hydrates a summary after the ordinary listing popup appears and
shares its request with the drawer. Late responses cannot replace a different
home's drawer. Failed requests can be retried by reopening it.

Successful snapshots expire after six hours; any unavailable source shortens
expiry to one minute. Cache identity includes the stored address, ZIP, city,
and coordinates. Source lookups run concurrently where independent, with
bounded timeouts. ZIMAS's slower address/profile requests have a 15-second
read budget; other requests have an eight-second budget. Cache reuse retains
the original “Records checked” timestamp rather than presenting it as a fresh
agency update. Permit source refresh dates are displayed separately.

The optional shared SQLite cache lives at `data/cache/property_context.sqlite`
and is capped at 2,048 snapshots. A small process cache also avoids disk reads.
Missing/corrupt/read-only cache storage does not prevent live lookups. No MLS
table migration, enrichment backfill, API key, or new dependency is required.
Delete that cache to force a new source lookup after changing adapter rules,
and bump its version prefix when changing payload or matching semantics.

## Verification

```bash
uv run pytest tests/test_property_context.py tests/test_docstring_depth.py
npx playwright test tests/e2e/property_context.spec.js
```

The source tests are offline and use an observed ZIMAS fixture without private
assessor fields. Browser tests stub agency context so coverage, focus, phone
layout, and failure handling do not depend on city service availability.
