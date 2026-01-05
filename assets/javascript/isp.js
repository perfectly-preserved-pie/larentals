// assets/00_isp.js
// Popup-driven ISP loader for Dash Leaflet popups (WSL2/Windows safe).
//
// Key points:
// - NO hardcoded host/port
// - Uses same-origin + Dash requests_pathname_prefix (works with VS Code port forwarding)
// - Exposes window.larentals.isp.{renderIspOptionsPlaceholderHtml, hydrateIspOptionsInPopup}

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
    // Normalize to no trailing slash (except when it's exactly "/")
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

    if (ispFetchCache.has(key)) {
      return ispFetchCache.get(key);
    }

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
        // Don’t cache failures; allow retry on next open.
        ispFetchCache.delete(key);
        throw err;
      });

    ispFetchCache.set(key, p);
    return p;
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
   *
   * @param {HTMLElement} popupRootEl - popup DOM element
   * @param {(options: unknown) => string} renderIspOptionsHtmlFn - your renderer from popup.js
   * @returns {void}
   */
  function hydrateIspOptionsInPopup(popupRootEl, renderIspOptionsHtmlFn) {
    const container = popupRootEl.querySelector('[data-isp-container="true"]');
    if (!container) return;

    if (container.getAttribute("data-loaded") === "true") return;

    const listingId = container.getAttribute("data-listing-id");
    if (!listingId) return;

    fetchIspOptionsForListing(listingId)
      .then((opts) => {
        container.innerHTML = renderIspOptionsHtmlFn(opts);
        container.setAttribute("data-loaded", "true");
      })
      .catch(() => {
        container.innerHTML = `<span style="color:#a00;">Failed to load</span>`;
      });
  }

  // Expose minimal API
  window.larentals = window.larentals || {};
  window.larentals.isp = {
    renderIspOptionsPlaceholderHtml,
    hydrateIspOptionsInPopup,
  };
})();
