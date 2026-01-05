// assets/00_isp.js
// Popup-driven ISP availability loader for Dash Leaflet popups.
// This is what's responsible for the "ISP Options" row in the popup.
// Uses same-origin + Dash requests_pathname_prefix (works with VS Code port forwarding)
// Exposes window.larentals.isp.{renderIspOptionsPlaceholderHtml, hydrateIspOptionsInPopup, renderIspOptionsHtml}

(function () {
  "use strict";

  /**
   * Escape text for safe HTML injection.
   * @param {unknown} value
   * @returns {string}
   */
  function escapeHtml(value) {
    const s = value === null || value === undefined ? "" : String(value);
    return s
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  /**
   * Normalize nullable strings.
   * @param {unknown} v
   * @returns {string|null}
   */
  function normalizeNullableString(v) {
    if (v === null || v === undefined) return null;
    const s = String(v).trim();
    return s.length ? s : null;
  }

  /**
   * Coerce unknown input into an array of objects.
   * @param {unknown} raw
   * @returns {Array<Record<string, unknown>>}
   */
  function coerceIspOptions(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw.filter((x) => x && typeof x === "object");
    return [];
  }

  /**
   * Get Dash's requests pathname prefix if app is mounted under a subpath.
   * Examples: "/" or "/larentals/".
   * @returns {string}
   */
  function getDashPrefix() {
    const cfg = window.__dash_config || {};
    const prefix = cfg.requests_pathname_prefix || cfg.url_base_pathname || "/";
    if (!prefix) return "";
    if (prefix === "/") return "";
    return prefix.endsWith("/") ? prefix.slice(0, -1) : prefix;
  }

  /**
   * Build a same-origin URL that respects Dash's prefix.
   * This is critical for WSL2 + Windows + VS Code port forwarding.
   * @param {string} path
   * @returns {string}
   */
  function buildSameOriginDashUrl(path) {
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    const prefix = getDashPrefix();
    return `${window.location.origin}${prefix}${cleanPath}`;
  }

  /**
   * Client-side cache so repeated popup opens don’t refetch.
   * Value is a Promise so concurrent opens share the same in-flight request.
   * @type {Map<string, Promise<Array<Record<string, unknown>>>>}
   */
  const ispFetchCache = new Map();

  /**
   * Fetch ISP options for a single listing id.
   * @param {string} listingId
   * @returns {Promise<Array<Record<string, unknown>>>}
   */
  function fetchIspOptionsForListing(listingId) {
    const key = String(listingId);

    const cached = ispFetchCache.get(key);
    if (cached) return cached;

    const url = buildSameOriginDashUrl(`/api/lease/isp-options/${encodeURIComponent(key)}`);

    const p = fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then((res) => {
        if (!res.ok) throw new Error(`ISP fetch failed (${res.status})`);
        return res.json();
      })
      .then((data) => coerceIspOptions(data))
      .catch((err) => {
        // Don’t cache failures; allow retry on next open
        ispFetchCache.delete(key);
        throw err;
      });

    ispFetchCache.set(key, p);
    return p;
  }

  /**
   * Format Mbps into a human-friendly string.
   * @param {number} mbps
   * @returns {string}
   */
  function formatMbps(mbps) {
    if (!Number.isFinite(mbps) || mbps <= 0) return "—";
    if (mbps >= 1000) {
      const gbps = mbps / 1000;
      const isWhole = Math.abs(gbps - Math.round(gbps)) < 1e-9;
      return `${isWhole ? Math.round(gbps) : gbps.toFixed(1)} Gbps`;
    }
    return `${Math.round(mbps)} Mbps`;
  }

  /**
   * Normalize an option row (handles both snake_case and FCC-ish column names).
   * @param {Record<string, unknown>} row
   * @returns {{ dba: string, service_type: string, max_dn_mbps: number, max_up_mbps: number }}
   */
  function normalizeOptionRow(row) {
    const dba = normalizeNullableString(row.dba ?? row.DBA) ?? "Unknown";
    const serviceType = normalizeNullableString(row.service_type ?? row.Service_Type) ?? "Unknown";

    const dn = Number(row.max_dn_mbps ?? row.MaxAdDn);
    const up = Number(row.max_up_mbps ?? row.MaxAdUp);

    return {
      dba,
      service_type: serviceType,
      max_dn_mbps: Number.isFinite(dn) ? dn : 0,
      max_up_mbps: Number.isFinite(up) ? up : 0,
    };
  }

  /**
   * Sort tiers best-to-worst.
   * @param {{ max_dn_mbps: number, max_up_mbps: number }[]} tiers
   * @returns {{ max_dn_mbps: number, max_up_mbps: number }[]}
   */
  function sortTiersDesc(tiers) {
    return [...tiers].sort((a, b) => {
      if (b.max_dn_mbps !== a.max_dn_mbps) return b.max_dn_mbps - a.max_dn_mbps;
      return b.max_up_mbps - a.max_up_mbps;
    });
  }

  /**
   * Rank service types for sorting and opinionation.
   * Higher is better.
   * @param {string} serviceType
   * @returns {number}
   */
  function serviceTypeRank(serviceType) {
    const s = String(serviceType || "").toLowerCase();
    if (s.includes("fiber")) return 400;
    if (s.includes("cable")) return 300;
    if (s.includes("fixed wireless")) return 200;
    if (s.includes("dsl")) return 100;
    if (s.includes("satellite")) return 50;
    return 0;
  }

  /**
   * Bucket groups into Best / Other / Fallback (opinionated).
   * @param {{ service_type: string, best_dn: number }} g
   * @returns {"best"|"good"|"fallback"}
   */
  function bucketGroup(g) {
    const s = String(g.service_type || "").toLowerCase();

    if (s.includes("fiber")) return "best";
    if (s.includes("cable") && g.best_dn >= 1000) return "best";

    if (s.includes("cable")) return "good";
    if (s.includes("fixed wireless") && g.best_dn >= 100) return "good";

    return "fallback";
  }

  /**
   * Group raw ISP rows into (provider + service_type) with tiers.
   * @param {Array<Record<string, unknown>>} raw
   * @returns {Array<{ key: string, dba: string, service_type: string, best_dn: number, best_up: number, tiers: Array<{max_dn_mbps:number, max_up_mbps:number}> }>}
   */
  function groupOptions(raw) {
    /** @type {Map<string, { dba: string, service_type: string, tiers: Array<{max_dn_mbps:number, max_up_mbps:number}> }>} */
    const m = new Map();

    for (const r of raw) {
      if (!r || typeof r !== "object") continue;
      const x = normalizeOptionRow(/** @type {Record<string, unknown>} */ (r));

      const key = `${x.dba}|||${x.service_type}`;
      if (!m.has(key)) m.set(key, { dba: x.dba, service_type: x.service_type, tiers: [] });

      const entry = m.get(key);
      entry.tiers.push({ max_dn_mbps: x.max_dn_mbps, max_up_mbps: x.max_up_mbps });
    }

    /** @type {Array<{ key: string, dba: string, service_type: string, best_dn: number, best_up: number, tiers: Array<{max_dn_mbps:number, max_up_mbps:number}> }>} */
    const groups = [];

    for (const [key, v] of m.entries()) {
      const tiers = sortTiersDesc(v.tiers);
      const best = tiers[0] || { max_dn_mbps: 0, max_up_mbps: 0 };

      groups.push({
        key,
        dba: v.dba,
        service_type: v.service_type,
        best_dn: best.max_dn_mbps,
        best_up: best.max_up_mbps,
        tiers,
      });
    }

    groups.sort((a, b) => {
      const ra = serviceTypeRank(a.service_type);
      const rb = serviceTypeRank(b.service_type);
      if (rb !== ra) return rb - ra;
      if (b.best_dn !== a.best_dn) return b.best_dn - a.best_dn;
      return a.dba.localeCompare(b.dba);
    });

    return groups;
  }

  /**
   * Render ISP options as opinionated buckets + expandable tiers (Option C + D).
   * @param {unknown} rawOptions
   * @returns {string}
   */
  function renderIspOptionsHtml(rawOptions) {
    const raw = coerceIspOptions(rawOptions);
    const groups = groupOptions(raw);

    if (!groups.length) {
      return `<span style="color:#666;">No ISP data</span>`;
    }

    /** @type {{ best: typeof groups, good: typeof groups, fallback: typeof groups }} */
    const buckets = { best: [], good: [], fallback: [] };

    for (const g of groups) {
      buckets[bucketGroup(g)].push(g);
    }

    /**
     * @param {string} title
     * @param {typeof groups} items
     * @returns {string}
     */
    function renderBucket(title, items) {
      if (!items.length) return "";

      const rows = items
        .map((g) => {
          const speed = `↓ ${escapeHtml(formatMbps(g.best_dn))} • ↑ ${escapeHtml(formatMbps(g.best_up))}`;
          const label = `${escapeHtml(g.dba)} — ${escapeHtml(g.service_type)}`;

          if (g.tiers.length > 1) {
            const tierLis = g.tiers
              .map((t) => {
                const tSpeed = `↓ ${escapeHtml(formatMbps(t.max_dn_mbps))} • ↑ ${escapeHtml(formatMbps(t.max_up_mbps))}`;
                return `<li style="margin:2px 0;">${tSpeed}</li>`;
              })
              .join("");

            return `
              <details style="margin:6px 0;">
                <summary style="cursor:pointer;">
                  <span style="font-weight:600;">${label}</span><br/>
                  <span style="color:#222;">${speed}</span>
                </summary>
                <div style="margin:6px 0 0 10px;">
                  <div style="color:#666; font-size:12px; margin-bottom:4px;">Available plans</div>
                  <ul style="margin:0; padding-left:16px;">${tierLis}</ul>
                </div>
              </details>
            `;
          }

          return `
            <div style="margin:6px 0;">
              <div style="font-weight:600;">${label}</div>
              <div style="color:#222;">${speed}</div>
            </div>
          `;
        })
        .join("");

      return `
        <div style="margin:8px 0;">
          <div style="font-weight:700; margin-bottom:4px;">${escapeHtml(title)}</div>
          ${rows}
        </div>
      `;
    }

    return (
      `<div>` +
      renderBucket("Best Available", buckets.best) +
      renderBucket("Other Good Options", buckets.good) +
      renderBucket("Fallback Options", buckets.fallback) +
      `</div>`
    );
  }

  /**
   * Render placeholder HTML to be inserted into the popup.
   * @param {unknown} listingIdRaw
   * @returns {string}
   */
  function renderIspOptionsPlaceholderHtml(listingIdRaw) {
    const listingId = normalizeNullableString(listingIdRaw);
    if (!listingId) {
      return `<span style="color:#666;">Unknown</span>`;
    }
    return `
      <div data-isp-container="true" data-listing-id="${escapeHtml(listingId)}">
        <span style="color:#666;">Loading…</span>
      </div>
    `;
  }

  /**
   * Hydrate the ISP placeholder within an opened popup.
   * @param {HTMLElement} popupRootEl
   * @returns {void}
   */
  function hydrateIspOptionsInPopup(popupRootEl) {
    const container = popupRootEl.querySelector('[data-isp-container="true"]');
    if (!container) return;

    if (container.getAttribute("data-loaded") === "true") return;

    const listingId = container.getAttribute("data-listing-id");
    if (!listingId) return;

    fetchIspOptionsForListing(listingId)
      .then((opts) => {
        container.innerHTML = renderIspOptionsHtml(opts);
        container.setAttribute("data-loaded", "true");
      })
      .catch((err) => {
        console.error("ISP options failed to load:", err);
        container.innerHTML = `<span style="color:#b00;">Failed to load ISP options</span>`;
      });
  }

  // Expose minimal API
  window.larentals = window.larentals || {};
  window.larentals.isp = {
    renderIspOptionsPlaceholderHtml,
    hydrateIspOptionsInPopup,
    renderIspOptionsHtml,
  };
})();
