# SQLite row diff

`data/runtime/larentals.db` → `data/runtime/larentals(3).db` (latest listing processing: October 2 → October 13, 2026).

Listings and enrichment are matched by unique, non-null MLS number. Updated means any stored column changed; columns are compared by name, not position. Read-only database connections were used.

| Table | Before | After | Net | Added | Removed | Updated | Unchanged |
|---|---:|---:|---:|---:|---:|---:|---:|
| _outlier_removal_report | 22 | 22 | 0 | 0 | 0 | 0 | 22 |
| buy | 7584 | 8069 | 485 | 665 | 180 | 2 | 7402 |
| buy_enrichment | 22420 | 23076 | 656 | 656 | 0 | 7378 | 15042 |
| buy_provider_options | 30778 | 32641 | 1863 | 2688 | 825 | unresolved | 29953 |
| buy_sample | 15 | 15 | 0 | 0 | 0 | 0 | 15 |
| lease | 3962 | 4136 | 174 | 470 | 296 | 3 | 3663 |
| lease_enrichment | 21915 | 22379 | 464 | 464 | 0 | 3655 | 18260 |
| lease_provider_options | 15759 | 16552 | 793 | 2023 | 1230 | unresolved | 14529 |
| lease_sample | 15 | 15 | 0 | 0 | 0 | 0 | 15 |
| listing_reports | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sqlite_sequence | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Provider option tables contain duplicate candidate keys. Their additions/removals are exact-row multiset differences (preserving duplicates); updates cannot be reliably distinguished from a removed old row and added new row.

## Listings by subtype

Updated counts use the subtype in the second database. Subtype transfers are shown separately and also count as updates. Unknown is a literal stored subtype; no main listing rows have NULL or blank subtypes.

### buy

| Subtype | Before | After | Net | Added | Removed | Updated | Transfers in | Transfers out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Condominium | 2766 | 2884 | 118 | 235 | 117 | 1 | 0 | 0 |
| Loft | 10 | 9 | -1 | 0 | 1 | 0 | 0 | 0 |
| Own Your Own | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| Single Family Residence | 962 | 1315 | 353 | 354 | 2 | 1 | 1 | 0 |
| Stock Cooperative | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 |
| Townhouse | 683 | 741 | 58 | 67 | 9 | 0 | 0 | 0 |
| Unknown | 3149 | 3106 | -43 | 9 | 51 | 0 | 0 | 1 |

### lease

| Subtype | Before | After | Net | Added | Removed | Updated | Transfers in | Transfers out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Apartment | 884 | 920 | 36 | 99 | 63 | 1 | 0 | 0 |
| Co-Op | 2 | 1 | -1 | 0 | 1 | 0 | 0 | 0 |
| Combo - Res & Com | 13 | 15 | 2 | 2 | 0 | 0 | 0 | 0 |
| Condominium | 704 | 809 | 105 | 144 | 39 | 0 | 0 | 0 |
| Duplex | 20 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| Loft | 4 | 4 | 0 | 1 | 1 | 0 | 0 | 0 |
| Own Your Own | 1 | 2 | 1 | 1 | 0 | 0 | 0 | 0 |
| Quadplex | 13 | 13 | 0 | 0 | 0 | 0 | 0 | 0 |
| Room For Rent | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| Single Family Residence | 856 | 992 | 136 | 181 | 45 | 1 | 0 | 0 |
| Stock Cooperative | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Studio | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| Townhouse | 297 | 326 | 29 | 39 | 10 | 1 | 0 | 0 |
| Triplex | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| Unknown | 1156 | 1022 | -134 | 3 | 137 | 0 | 0 | 0 |

### buy_sample

| Subtype | Before | After | Net | Added | Removed | Updated | Transfers in | Transfers out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Condominium | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| Townhouse | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Unknown | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |

### lease_sample

| Subtype | Before | After | Net | Added | Removed | Updated | Transfers in | Transfers out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Apartment | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| Condominium | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Unknown | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |

## Update details

- buy MLS MB26180857MR: date_processed; listing_input_hash; scrape_status; image_status; geocode_status; has_ac; has_dishwasher.
- buy MLS RS26202717MR: zip_code; subtype; date_processed; full_street_address; listing_input_hash; geocode_status.
- lease MLS P1-29049PF: date_processed; listing_input_hash; geocode_status.
- lease MLS PF26210250PF: security_deposit; list_price; ppsqft; date_processed; listing_input_hash; geocode_status.
- lease MLS RS26207229MR: date_processed; listing_input_hash; geocode_status; has_ac; has_dishwasher.

Buy enrichment: all 7,378 updates change only source_version and enriched_at. Lease enrichment: all 3,655 updates change those metadata fields; some also change school fields (132 high-school names, 63 middle-school names, 14 district names/types, 11 elementary-school names; counts can overlap).

## Known subtype coverage

| Listings | Known before | Known after | Net known | Unknown before | Unknown after |
|---|---:|---:|---:|---:|---:|
| buy | 4435 | 4963 | +528 | 3149 | 3106 |
| lease | 2806 | 3114 | +308 | 1156 | 1022 |
