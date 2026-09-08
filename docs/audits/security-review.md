# Security review of agent-readiness changes

Reviewed September 8, 2026. This was a focused source review and isolated exploit
reproduction, not a full penetration test or deployment/infrastructure assessment.
No application code was changed by this review. All write probes used a disposable
SQLite fixture; the browser XSS proof used intercepted mock responses and no live data.

## Findings

### 1. Existing stored-XSS sink in property popups — high impact if listing data is attacker-controlled

`assets/js/popup.js` interpolates database fields into HTML without consistently
escaping text or validating URL schemes. Examples include subtype at line 575,
lease terms at line 571, address/link URLs at lines 398–407, and image URLs at
line 422. The popup content is passed to Leaflet's HTML rendering.

An isolated Chromium test loaded the actual popup script, supplied a mocked listing
response whose subtype contained an image with an `onerror` handler, and triggered
`on_each_feature`'s popup-open callback. The handler executed and set a harmless
JavaScript sentinel. The earlier SVG-onload probe did not fire; the image-error
probe confirmed execution.

Exploitability requires a malicious value to reach the listing dataset or listing
response. This does not show that an anonymous caller can edit listing fields.
The affected script is unchanged from HEAD, so this is pre-existing, not introduced
by the REST search or developer pages.

Fix all text and attribute interpolations, allow only approved URL schemes for
links/images, and prefer DOM textContent/attribute APIs over HTML strings. Test
both rental and sale popups with malicious source fields. CSP is defense in depth,
not a replacement for output encoding.

### 2. New REST search has no application-level request limit — medium availability risk

`api/public.py:209` exposes unauthenticated searches. Each call executes a count,
a filtered/sorted listing query, and a freshness query. The page-size cap limits
returned rows, not the amount of database work. Existing MCP-only limits do not
apply to this route. No load or denial-of-service test was performed, and hosting
or CDN controls may provide limits not represented in this checkout.

Add enforced limits at a trusted proxy or through shared application state across
Gunicorn workers. Consider bounded caching and query time budgets. Keep reads
public if that remains the product requirement.

### 3. Oversized integers cause HTTP 500 — low severity input-validation defect exposed by the new REST route

`api/public.py:65` accepts arbitrarily large positive integers for price and several
other filters. The existing shared query passes them to SQLite, which only accepts
signed 64-bit integer parameters.

Reproduction against the disposable fixture:

```text
GET /api/listings?listing_type=lease&max_price=9223372036854775808
500 application/json, error.code=internal_error
```

The maximum signed value, 9223372036854775807, succeeds. The error is generic and
did not disclose SQL or filesystem paths, but repeated invalid requests generate
avoidable exceptions/logging. Reject out-of-range numeric filters with 400 before
SQL execution and publish matching maximums in OpenAPI. The shared MCP validator
should apply the same bound.

### 4. Existing anonymous report endpoint can be abused — medium integrity/resource risk

`api/report_listing.py:44` accepts unauthenticated reports. In a temporary database,
an anonymous valid report for fixture listing L1 returned 200, and
`get_reported_inactive_mls_numbers` then returned L1. The data pipelines persist
these reports into `reported_as_inactive` flags without an approval step visible
in the reviewed code. This review does not claim that the flag immediately hides
a listing in the current UI.

The request body is parsed before text is sanitized and length-checked; no
application-wide body-size limit is configured. A page_path beginning with /buy
also has no length limit. This behavior predates the agent work, although the new
OpenAPI document makes the endpoint easier to discover.

Use report-specific request size/rate limits and validate field lengths before
sanitization. Decide whether moderation or a stronger abuse-control mechanism is
needed before accepting reports into authoritative listing status. CORS alone
does not protect this endpoint from direct scripted clients.

## Checks without findings in the new code

- SQL injection strings in location/property_type returned zero matches, not
  broadened result sets. Injected listing_type/sort values returned 400. Table
  and sort choices are allowlisted; values use bound parameters.
- A write attempted through the search connection was rejected by SQLite.
  Search uses URI mode=ro and PRAGMA query_only=ON.
- Query-string HTML and a spoofed Host did not inject content into the new raw
  HTML. Canonical metadata retained the configured site origin.
- Reflected validation messages were sent as application/json, not executable
  HTML. Unexpected API failures return generic messages.
- New static content is escaped and selected from fixed page definitions.
  No new server-side URL-fetching or shell-execution path was found.

The 98/100 Is Agentic tunnel result is not a security score and does not cover
these findings. Production edge controls, dependency vulnerability scanning,
all ingestion paths, and a complete application penetration test are outside
this focused review.

References: [Flask security and resource limits](https://flask.palletsprojects.com/en/stable/web-security/),
[SQLite integer representation](https://www.sqlite.org/c3ref/int64.html).
