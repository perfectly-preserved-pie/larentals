SQLite comparison: October 30, 2026

Before: `data/runtime/larentals.db` (file modified October 24; newest listing processing October 23).
After: `data/runtime/larentals(1).db` (file modified October 30; newest listing processing October 29).

Both databases were opened read-only, pass `PRAGMA quick_check`, and have identical schemas, including indexes. SHA-256 hashes stayed unchanged during the comparison and are recorded in [summary.json](summary.json).

Rows were matched by MLS number for listings, samples, and enrichment. Provider rows were matched by `(listing_id, DBA, TechCode, Service_Type)`; outlier report rows by `(table_name, column_name)`. Every selected key is unique within each input. Changed means a matched row differs in at least one column; added and removed rows are counted separately. Row order and SQLite rowids are ignored.

| Table | Before | After | Added | Removed | Changed | Unchanged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| _outlier_removal_report | 22 | 22 | 0 | 0 | 0 | 22 |
| buy | 7,327 | 7,445 | 487 | 369 | 1,998 | 4,960 |
| buy_enrichment | 23,664 | 24,140 | 476 | 0 | 6,916 | 16,748 |
| buy_provider_options | 29,628 | 30,042 | 1,912 | 1,498 | 0 | 28,130 |
| buy_sample | 15 | 15 | 0 | 0 | 0 | 15 |
| lease | 3,789 | 3,973 | 421 | 237 | 660 | 2,892 |
| lease_enrichment | 22,824 | 23,237 | 413 | 0 | 3,526 | 19,298 |
| lease_provider_options | 15,261 | 16,062 | 1,782 | 981 | 0 | 14,280 |
| lease_sample | 15 | 15 | 0 | 0 | 0 | 15 |
| listing_reports | 0 | 0 | 0 | 0 | 0 | 0 |
| sqlite_sequence | 0 | 0 | 0 | 0 | 0 | 0 |

Main inventory totals: **908 added, 606 removed, 2,658 changed, 7,852 unchanged**. Inventory grew from 11,116 to 11,418 listings (+302).

**The subtype backfill worked, but coverage is incomplete.** All 2,658 changed retained listings recovered an `Unknown` subtype. No retained listing changed from a known subtype to another known subtype or back to missing.

| Market | Unknown before | Old unknowns retained | Recovered | Old unknowns still missing | Unknown removed | New unknowns added | Unknown after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| buy | 2,343 | 2,177 | 1,998 | 179 | 166 | 16 | 195 |
| lease | 845 | 791 | 660 | 131 | 54 | 12 | 143 |

Buy recovered 1,998 of 2,177 retained unknowns (91.8%): 1,980 Single Family Residence and 18 Condominium. Lease recovered 660 of 791 retained unknowns (83.4%): 386 Condominium, 264 Single Family Residence, 9 Townhouse, and 1 Co-Op.

There are **338 unknown subtypes remaining**: 195 buy and 143 lease. Of these, 310 persisted from the old inventory and 28 are newly added listings. The overall unknown count fell from 3,188 to 338; that decrease also includes 220 unknown listings removed from inventory, so it is not the recovery count.

Exactly 2,657 retained listings changed only their subtype. Buy MLS `SR26207958MR` also had address whitespace normalized, `date_processed` refreshed, and `listing_input_hash` changed. No retained listing price changed.

These snapshots establish that subtype recovery was persisted. They do not establish which unresolved rows lack source data or had failed/pending lookups. The available local buy/lease checkpoints have no subtype-outcome columns, and no standalone subtype checkpoint is present. This comparison made no API requests.

**Sample tables are stale.** `buy_sample` and `lease_sample` are unchanged; four buy sample rows and one lease sample row still say `Unknown` although their main-table subtype is now populated:

| Sample table | MLS | Sample subtype | Main-table subtype |
| --- | --- | --- | --- |
| buy_sample | 26860961 | Unknown | Single Family Residence |
| buy_sample | IN26159369MR | Unknown | Single Family Residence |
| buy_sample | SR26160233MR | Unknown | Single Family Residence |
| buy_sample | PW26157711MR | Unknown | Single Family Residence |
| lease_sample | 26861913 | Unknown | Condominium |

Other changes: `buy_enrichment` added 476 rows and updated 6,916 rows only in `source_version` and `enriched_at`. `lease_enrichment` added 413 rows and updated 3,526 rows; all changed metadata, with school district name/type also changing on 47 rows, nearest middle school on 27, and nearest elementary school on 5 (these groups can overlap). Neither enrichment table lost rows. Provider options have additions/removals as shown above and no changes under the composite keys. The outlier report and listing reports are unchanged.

Every table has these exports (empty categories include headers):

- `<table>.added.csv`: complete new rows.
- `<table>.removed.csv`: complete removed rows.
- `<table>.changes.csv`: one row per changed cell, with before/after JSON preserving SQL null versus empty text.
- `<table>.changed_rows.jsonl`: complete before/after snapshots for every changed row.

Listing exports:

| Market | Added | Removed | Changed cells | Full changed rows | Subtype transitions | Remaining unknowns |
| --- | --- | --- | --- | --- | --- | --- |
| buy | [CSV](buy.added.csv) | [CSV](buy.removed.csv) | [CSV](buy.changes.csv) | [JSONL](buy.changed_rows.jsonl) | [CSV](buy.subtype_transitions.csv) | [CSV](buy.remaining_missing_subtypes.csv) |
| lease | [CSV](lease.added.csv) | [CSV](lease.removed.csv) | [CSV](lease.changes.csv) | [JSONL](lease.changed_rows.jsonl) | [CSV](lease.subtype_transitions.csv) | [CSV](lease.remaining_missing_subtypes.csv) |

All export row counts reconcile with the summary. Independent SQL joins confirmed listing additions, removals, changed rows, and subtype recoveries. The databases were not modified.
