# WhereToLive.LA agent readiness

The implementation makes the existing listing dataset discoverable through raw HTML,
Markdown, REST, OpenAPI, and the existing MCP search tool. The maps still mount into
the same React entry point; React replaces the readable initial content after loading.
The title card has one Developers link using the existing style. The developer guide
groups REST API, MCP setup, and CLI resources; the existing `/mcp` and `/_mcp` URLs remain available.

## Audit coverage

| Requested fix | Implementation or remaining action |
| --- | --- |
| 1. Content without JavaScript | Homepage has over 1,100 characters of actual descriptive prose, an H1, and sequential H2 sections. Rental, sale, and MCP pages include initial content inside the React mount point. Framework scripts and configuration remain necessary for the interactive app. |
| 2. Real 404s | Unknown Dash catch-all paths return HTTP 404 with Markdown links to sitemap, llms.txt, and developers. Framework routes and registered API methods retain their handlers. |
| 3. OpenAPI | `/openapi.json` is a validated OpenAPI 3.1.1 document describing all seven REST operations. |
| 4. JSON errors | Existing and new API failures include `status`, `message`, and `error: {code, message, hint}`; HTTP statuses and Allow headers are preserved. Unexpected exception details are logged, not returned. |
| 5. MCP resources | The server is intentionally tool-only. The legacy initialize response now omits unsupported resources; modern discovery already advertised only tools. No placeholder resources were added. |
| 6. Markdown | Seven public pages support HTML/Markdown negotiation, quality values, wildcards, explicit exclusions, and 406. Both variants include `Vary: Accept`, preserving compression variation. |
| 7. Brand search | Canonical identity, brand titles, social image, Organization schema, and discoverable guides are implemented. Search ranking and indexing require external follow-up. |
| 8. Public API | `/api` advertises unauthenticated REST and MCP; `/api/listings` wraps the existing validated, read-only, parameterized query. |
| 9–10. Developer portal and homepage links | `/developers` includes authentication, examples, filters, errors, usage limits, CLI, MCP, and a working read-only search form. A Developers link is available before and after React mounts. No keys are needed. The explorer uses live data; there is no separate sandbox deployment. |
| 11. Agent instructions | `/llms.txt` includes specific when-to-use guidance, calling instructions, pagination, attribution, and limitations. |
| 12. Organization | Existing contact email, contactPoint, name, URL, and source repository are published. A PostalAddress remains intentionally absent until a real public address is supplied. |
| 13. Trust pages | `/about`, `/contact`, `/privacy` each have more than 500 characters of factual content. Privacy text describes report storage, local theme state, analytics, external assets, and operational logs visible in this repository. |
| 14. Developer discoverability | Brand titles, homepage links, llms.txt links, predictable paths, and sitemap coverage are present. Search-engine indexing remains external. |
| 15–16. Schemas/function calling | Every operation has a unique operationId, description, typed inputs, and response schemas. Search result schemas are derived from the existing Python TypedDict definitions. Actual lease and buy responses are validated. |
| 17. Metadata | Language, canonical URL, og:type, and a reachable 1200×630 social image are present. Conflicting empty Dash Open Graph tags are removed. |
| 18. CLI | `wheretolive-search` is a working source-installed console command with JSON output and meaningful exit codes. Registry publication needs a release decision and credentials. The existing `wheretolive-la` server command is unchanged. |

## Verification

Verified locally on September 8, 2026: **243 Python tests passed** (plus four
subtests), **16 browser tests passed**, and **42 HTTP response cases passed**.
The sole failing Python test is the pre-existing documentation check described
below. `git diff --check` and `uv lock --check` also pass; existing locked package
versions are unchanged. The installed CLI was exercised against the local API.


- The regression suite covers raw HTML, Markdown parity, content negotiation and cache
  headers, strict paths, framework route preservation, schema validation, search
  pagination/filter errors, JSON failures, MCP capabilities, and CLI behavior.
- Browser checks cover all seven pages with JavaScript disabled; rental and sale map
  mounting; the API link and search form; and existing desktop, tablet, and mobile
  filter behavior.
- `python -m scripts.verify_agent_endpoints` checks 42 response cases, covering every
  public page, machine-readable discovery file, all documented REST operations, the
  image, health check, missing paths, and both MCP transport versions. It uses a
  deliberately invalid report body so it does not insert reports.
- The repository-wide documentation test has 41 existing violations in unrelated
  functions. The same failures reproduce from `HEAD`; the new functions meet that
  test's documentation requirements.

## Rollout and owner decisions

Deploy the reviewed code using the existing deployment process, then rerun the endpoint
verification command with `--base-url https://wheretolive.la`. The local implementation
has not been published or assigned a new Is Agentic score. Purge any previously cached
app-shell responses for missing paths, and ensure the hosting proxy preserves origin
404 statuses and `Vary: Accept`.

A verified public mailing address is needed to complete PostalAddress. Do not substitute
the service area or a private address. Confirm the privacy text against hosting and
analytics configuration; retention periods and any additional commitments require the
operator's decision.

Use the domain owner's search-console credentials to submit the sitemap and request
indexing of the developer and trust pages. Consistent public branding, legitimate
listings, and relevant earned links can support discoverability; code cannot guarantee
brand-search placement.

Decide whether to publish this full project or a separately packaged lightweight CLI,
then configure the chosen npm/PyPI/Homebrew release credentials. A separate sandbox,
API-key tier, REST quotas, and service-level commitments are optional product decisions;
the current public search is read-only and requires no credentials.

## Protocol references

- [Markdown negotiation requirements](https://acceptmarkdown.com/)
- [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [MCP 2025-11-25 resources capability](https://modelcontextprotocol.io/specification/2025-11-25/server/resources)
