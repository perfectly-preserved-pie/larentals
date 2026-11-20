import { parseArgs } from "node:util";
import { audit, renderText } from "@agentmarkup/audit";

const canonicalOrigin = "https://wheretolive.la";
const { values } = parseArgs({
  options: {
    port: { type: "string", default: "8050" },
    json: { type: "boolean" },
  },
});

const port = Number(values.port);
if (!/^\d+$/.test(values.port) || port < 1 || port > 65535) {
  console.error("Pass --port with a port number from 1 to 65535.");
  process.exit(2);
}
const localOrigin = `http://127.0.0.1:${port}`;

/**
 * Fetch an audit resource from the dev server with its public identity intact.
 * AgentMarkup compares canonical URLs and sitemap entries against the target
 * origin. Remap only that origin and disable redirect following so a local
 * response cannot send the audit to production or another service.
 *
 * @param {string} requestedUrl Public URL used as an audit input.
 * @param {RequestInit} init Request options supplied by the audit.
 * @returns {Promise<Response>} Response from the loopback dev server.
 */
function fetchLocal(requestedUrl, init) {
  const url = new URL(requestedUrl);
  if (url.origin !== canonicalOrigin) {
    throw new Error(`Audit URL is outside the canonical origin: ${url.origin}`);
  }
  return fetch(localOrigin + url.pathname + url.search, { ...init, redirect: "manual" });
}

/**
 * Adapt a local response to AgentMarkup's crawler probe format.
 * Preserve the crawler user agent and response status so the audit can compare
 * what each crawler sees, including real 404s and redirects.
 *
 * @param {string} requestedUrl Public URL for the crawler probe.
 * @param {object} options Probe user agent and optional timeout.
 * @returns {Promise<object>} Status, headers, and content used by the analyzers.
 */
async function probeLocal(requestedUrl, { userAgent, timeoutMs = 10_000 }) {
  const response = await fetchLocal(requestedUrl, {
    headers: { "user-agent": userAgent },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await response.text();
  return {
    requestedUrl,
    finalUrl: requestedUrl,
    status: response.status,
    ok: response.ok,
    headers: Object.fromEntries(response.headers),
    body,
    bodyBytes: Buffer.byteLength(body),
    redirects: 0,
    blocked: false,
  };
}

try {
  const report = await audit(canonicalOrigin, {
    fetchedAt: new Date().toISOString(),
    score: true,
    fetchImpl: probeLocal,
    collect: { fetchImpl: fetchLocal, minGapMs: 0 },
  });
  if (values.json) {
    console.log(JSON.stringify({ localOrigin, ...report }, null, 2));
  } else {
    console.log(`Audited local dev server at ${localOrigin}`);
    console.log(renderText(report));
  }
  process.exitCode = report.summary.error ? 1 : 0;
} catch (error) {
  console.error(`Local audit failed for ${localOrigin}. Check that the dev server is running.`);
  console.error(error.cause?.message ?? error.message);
  process.exitCode = 2;
}
