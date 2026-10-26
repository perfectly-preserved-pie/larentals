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

## Loading and server snapshots

Listing details, property records, and popup housing summaries read local data
only. A cache miss returns an explicit “not prepared yet” state. No popup HTTP
request can start an agency lookup, even with a single synchronous web worker.
The existing LAHD records drawer retains its separate APN detail lookup.

The browser loads saved property and housing summaries independently after
the ordinary listing appears. Late responses cannot replace another home's
records. Every source retains its own last successful check time. Older records
remain readable during outages and are labeled as awaiting an update. A failed
refresh cannot overwrite successful facts with an empty or unavailable result.

Snapshots live in the `property_snapshots` table inside
`data/cache/property_context.sqlite`. Unlike the old six-hour request cache,
these records do not expire or have a 2,048-property eviction cap. Share this
file between the refresh process and web workers, and keep it on a persistent
volume when deploying containers. A still-fresh legacy cache can be read during
migration, without starting any network work.

### Source cadence and our refresh targets

| Source | Published source cadence | Our check interval |
| --- | --- | --- |
| LA City issued building permits | Weekly in the city's dataset metadata | Weekly |
| LAHD investigation and violation feeds | Quarterly in the city's metadata | Weekly, to catch out-of-cycle publications |
| CAL FIRE hazard maps | Formal map releases; current service versions are 2024 SRA and 2025 LRA | Weekly |
| FEMA NFHL | Changes as effective maps and revisions are incorporated; no fixed cadence verified here | Daily |
| ZIMAS parcel profile | Multiple contributing city datasets; no single guaranteed cadence verified here | Daily |

These are refresh policies, not claims that the agencies publish new records
at each interval. Permit feed refresh dates remain separate from our check time.

### Refresh job

Run the job after importing listings, then schedule a daily invocation. Existing
sections inside their check interval are reused. Uncached and newer properties
are prioritized for a limited backfill; relistings with identical address and
location share a snapshot. Each property commits separately so interrupted
backfills can resume.

```bash
# Warm all current listings independently of the app server.
uv run refresh-property-snapshots

# Recover selected listings or run a limited backfill.
uv run refresh-property-snapshots --mls 26991311 --mls 26996609
uv run refresh-property-snapshots --limit 100 --workers 2

# Force a source refresh regardless of its check interval.
uv run refresh-property-snapshots --mls 26991311 --force
```

Example cron entry for the server running this checkout (3:15 AM in the cron
daemon's timezone). The lock avoids overlapping long initial backfills:

```cron
15 3 * * * cd /home/straying/larentals && flock -n /tmp/larentals-property-refresh.lock uv run refresh-property-snapshots >> /home/straying/larentals/property-refresh.log 2>&1
```

This repository supplies the refresh command; installing a host scheduler or
mounting production volumes is part of deployment. Initial backfills contact
agencies and can take time, but they never occupy a web request worker. Source
concurrency is bounded, and failed attempts wait an hour before another normal
maintenance run retries them. `--force` bypasses that cooldown for recovery.

## Verification

```bash
uv run pytest tests/test_property_context.py tests/test_property_snapshots.py tests/test_docstring_depth.py
npx playwright test tests/e2e/property_context.spec.js
```

The source tests are offline and use an observed ZIMAS fixture without private
assessor fields. Browser tests stub agency context so coverage, focus, phone
layout, and failure handling do not depend on city service availability.
