# Is Agentic audit of the local changes

Run on September 8, 2026 using the official npm CLI:

```bash
npx --yes is-agentic@1.0.1 https://lip-patches-justice-vehicles.trycloudflare.com --json
```

The official report returned **98/100**, versus the stored production report's **43/100**: an observed increase of **55 points**. This is a provisional tunnel result, not a verified new production score.

[Before report](https://is-agentic.com/scan/wheretolive.la) · [Local tunnel report](https://is-agentic.com/scan/lip-patches-justice-vehicles.trycloudflare.com)

## What passed

The local report records 10/10 applicable Essential checks passing (80/80 points), 15.8/20 Recommended points, and 2.5 bonus points. Confirmed technical improvements include readable HTML, real Markdown 404s, OpenAPI, JSON API errors, Markdown negotiation, trust pages, metadata, and schema compatibility.

## Comparison limits and scanner errors

- The temporary trycloudflare.com hostname caused Ora to attribute Cloudflare packages to this app. It incorrectly credited cloudflare-cli, SDK packages, and a Cloudflare MCP package. These are not WhereToLive.LA features.
- The scanner did not detect our actual /_mcp server. Its resources check became not applicable, rather than independently verifying the handshake correction. Local HTTP and protocol regression checks previously verified both supported MCP transports.
- Canonical URLs, llms.txt links, sitemap links, and the OpenAPI server URL still correctly identify wheretolive.la. Some probes therefore reached the unchanged production deployment. The report describes the developer page as thin/unreachable despite its verified local content.
- Brand and developer-search rankings cannot be assessed fairly against a new temporary hostname.
- The eligible check sets differ: 27 before, 32 after. Do not interpret the 55-point difference as a controlled production measurement.

## Remaining actionable findings

- Declare an API versioning and deprecation policy.
- Add actual REST request limits and corresponding headers if the product adopts a quota policy; do not publish fictional limits.
- Supply a verified public organization postal address.
- Deploy and rescan wheretolive.la for an authoritative production comparison and genuine brand/indexing results.

## Original requested fixes: scanner evidence

| Check | Before | Tunnel scan |
| --- | --- | --- |
| Content without JavaScript | failed | pass |
| Agent-friendly 404s | failed | pass |
| OpenAPI spec published | failed | pass |
| JSON error responses | failed | pass |
| MCP resources exposed | failed | na |
| Markdown content negotiation (acceptmarkdown.com) | failed | pass |
| Brand name discoverability | failed | fail |
| Public API with reachable endpoints | failed | pass |
| Developer portal | failed | pass |
| Public API/docs linked from homepage | failed | warning |
| Agent instruction / when-to-use | failed | pass |
| Organization schema completeness | failed | warning |
| Trust anchor pages | failed | pass |
| Developer resource discoverability | partial | warning |
| API schema complexity analysis | partial | pass |
| Function calling compatibility | partial | pass |
| Metadata completeness | partial | pass |
| CLI tool available | partial | pass |

For interpretation, the CLI/SDK and MCP statuses above must be read with the attribution caveats. Raw reports are saved beside this file. The temporary tunnel was used only for the audit and is closed after retrieving the results.

Sources: [Is Agentic CLI documentation](https://is-agentic.com/docs), [Is Agentic methodology](https://is-agentic.com/methodology), [Ora localhost/tunnel workflow](https://ora.ai/docs).
