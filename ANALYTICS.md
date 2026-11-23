# WhereToLive.LA analytics

Rybbit site **wheretolive.la** uses numeric site ID **1**. Market events use
`page=lease` for `/` and `page=buy` for `/buy`. Keep those markets separate when
comparing behavior. For revised events, use `schema_version=2` and a time range
after the instrumentation was deployed. Check the event payloads before using
historical data. Older rows can be missing properties, and old callback-based
`Filter Changed` could miss price edits or count Location and Listed Date together.

Filter events below also include `layout` (`sidebar`, `side-drawer`, or
`bottom-sheet`). Layout is a property of the UI. Use Rybbit's device type for
hardware comparisons.

| Event | Meaning | Properties beyond page, version, and filter layout |
| --- | --- | --- |
| Filter Panel Viewed | First exposure to a mounted panel in a layout | |
| Filter Section Opened | User expands a collapsed accordion | `section_id`, `section`, `source` (`header` or `quick_filter`) |
| Filter Changed | A draft filter group changed | `category`, `section_id` |
| Filter Search Committed | Applied filters were evaluated after any pending location lookup, including zero matches | `commit_mode` (`explicit` or `automatic`), `result_bucket`, `has_results`, `active_filter_count`, `has_active_filters` |
| Filter Group Committed | One event per changed group in a committed search | `category`, `section_id`, `commit_mode`, `is_active` (false when cleared or when the location has no usable ZIP match) |
| Location Added | Submitted location entry | `method` |
| Location Resolved | Resolver returned a usable ZIP match | `method`, `outcome` (`resolved` or `partial`) |
| Location Resolution Failed | Resolver returned no usable match | `method`, `error` (bounded reason code) |
| Listing Opened | Listing popup opened | `source` (`map_pin` or `results_list`) |
| Listing Link Clicked | Provider link activated | `activation` (`primary` includes keyboard activation, `middle` covers middle-clicks) |

Listing events carry `page` and `schema_version`. The legacy `Filters Applied`
event counts explicit Apply, including confirmations where no filter changed.
Use `Filter Search Committed` to compare both commit modes.

## How to answer product questions

- For sidebar priority, start with distinct sessions that saw the panel in the
  same market, layout, and date range. For each group, measure the share of
  those sessions with `Filter Group Committed` and `is_active=true`. Use section
  opens to study discoverability and draft edits to study exploration. Joining on
  `section_id` matches the accordion even when its analytics category differs.
- For results quality, calculate the share of committed searches where
  `has_results=false`. State the time window and the number of sessions or
  events behind each comparison.
- For listing behavior, use the saved Map to provider and Filters to provider
  funnels for Rentals and Buy. **Listing provider clicked** measures the
  outbound handoff. **Search narrowed with results** requires both
  `has_active_filters=true` and `has_results=true`.

## Tracking changes

Keep event and property names stable for saved reports. Version changes that
alter how a metric should be interpreted, update this table, and record the
deployment boundary for any before/after analysis. Send only bounded event
properties. Omit typed locations, addresses, listing identifiers, and exact
filter values. Verify the captured payload on a test page with a stubbed SDK.

The filter contract is implemented in
[responsive_filters.js](assets/js/clientside_callbacks/responsive_filters.js).
Listing events and the Rybbit/Plausible dispatch are wired through
[popup.js](assets/js/popup.js) and
[plausible_events.js](assets/js/clientside_callbacks/plausible_events.js).
