// This is a JavaScript file to customize the Leaflet popup.
// It should be used with dl.GeoJSON's `onEachFeature` option.
// See https://github.com/perfectly-preserved-pie/larentals/issues/86#issuecomment-1585304809

/**
 * @typedef {{ properties?: Record<string, unknown> }} PopupFeature
 */

/**
 * @typedef {{
 *   bindPopup: (content: string, options?: Record<string, unknown>) => unknown,
 *   on: (eventName: string, handler: () => void) => unknown,
 *   getPopup?: () => ({
 *     getElement?: () => HTMLElement | null,
 *     setContent?: (content: string) => unknown,
 *   } | null),
 *   _map?: { getContainer?: () => HTMLElement | null } | null,
 * }} PopupLayer
 */

(function () {
    "use strict";

    /** @type {Map<string, Promise<Record<string, unknown>>>} */
    const listingDetailFetchCache = new Map();

    document.addEventListener("click", function trackListingLinkClick(event) {
        const target = event.target;
        const link = target && typeof target.closest === "function"
            ? target.closest(".plausible-listing-link")
            : null;
        if (link) {
            window.larentals?.analytics?.trackListingLinkClicked();
        }
    });

    /**
     * Escape text for safe HTML interpolation.
     *
     * @param {unknown} value Raw text value.
     * @returns {string} Escaped string.
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
     *
     * @param {unknown} value Raw string-like value.
     * @returns {string|null} Trimmed string or `null`.
     */
    function normalizeNullableString(value) {
        if (value === null || value === undefined) return null;
        const normalized = String(value).trim();
        if (!normalized || ["none", "null", "nan"].includes(normalized.toLowerCase())) {
            return null;
        }
        return normalized;
    }

    /**
     * Normalize a listing identifier while preserving leading zeroes.
     *
     * @param {unknown} value Listing id / MLS value.
     * @returns {string} Normalized identifier string.
     */
    function normalizeListingId(value) {
        if (value === null || value === undefined) return "";
        return String(value).trim().replace(/\.0$/, "");
    }

    /**
     * Strip a terminal `.0` without disturbing meaningful decimals.
     *
     * @param {string|number|null|undefined} value String or numeric display value.
     * @returns {string|number|null|undefined} Cleaned display value.
     */
    function stripTrailingPointZero(value) {
        if (value === null || value === undefined) return value;
        const cleaned = String(value).replace(/\.0$/, "");
        if (typeof value === "number") {
            const asNum = Number(cleaned);
            return Number.isNaN(asNum) ? value : asNum;
        }
        return cleaned;
    }

    /**
     * Format lot size with separators while preserving up to two decimals.
     *
     * @param {unknown} value Raw lot size value.
     * @returns {string|null} Human-readable lot size or `null`.
     */
    function formatLotSize(value) {
        if (value === null || value === undefined) return null;
        if (typeof value === "string") {
            const normalized = value.replace(/,/g, "").trim();
            if (!normalized || ["none", "null", "nan"].includes(normalized.toLowerCase())) {
                return null;
            }
            const num = Number(normalized);
            if (Number.isNaN(num)) return null;
            const formatted = num % 1 === 0
                ? num.toLocaleString("en-US")
                : num.toLocaleString("en-US", { maximumFractionDigits: 2 });
            return stripTrailingPointZero(formatted);
        }

        const num = Number(value);
        if (Number.isNaN(num)) return null;
        const formatted = num % 1 === 0
            ? num.toLocaleString("en-US")
            : num.toLocaleString("en-US", { maximumFractionDigits: 2 });
        return stripTrailingPointZero(formatted);
    }

    /**
     * Format a numeric value as US currency without decimals.
     *
     * @param {unknown} value Raw currency-like value.
     * @returns {string} Currency string or `"Unknown"`.
     */
    function formatCurrency(value) {
        if (value === null || value === undefined || value === "") return "Unknown";

        const n = Number(value);
        if (!Number.isFinite(n)) return "Unknown";

        return `$${n.toLocaleString()}`;
    }

    /**
     * Format a 0/1-like flag as Yes / No / Unknown.
     *
     * @param {unknown} value Raw boolean-like value.
     * @returns {string} Human-readable flag label.
     */
    function formatYesNoUnknown(value) {
        if (value === null || value === undefined || value === "") return "Unknown";

        const normalized = String(value).trim().toLowerCase();
        if (["1", "true", "yes", "y"].includes(normalized)) return "Yes";
        if (["0", "false", "no", "n"].includes(normalized)) return "No";
        return "Unknown";
    }

    /**
     * Format a miles distance for popup display.
     *
     * @param {unknown} value Raw miles value.
     * @returns {string} Formatted miles or `Unknown`.
     */
    function formatMiles(value) {
        if (value === null || value === undefined || value === "") return "Unknown";

        const n = Number(value);
        if (!Number.isFinite(n)) return "Unknown";
        return `${n.toFixed(2)} mi`;
    }

    /**
     * Format a numeric value as a localized integer.
     *
     * @param {unknown} value Raw numeric value.
     * @returns {string} Localized integer string.
     */
    function formatWholeNumber(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return "0";
        return Math.round(n).toLocaleString("en-US");
    }

    /**
     * Render the Dash drawer trigger for a matched Housing Department property.
     *
     * @param {Record<string, unknown>} summary Housing Department property summary.
     * @returns {string} HTML drawer trigger or empty string.
     */
    function renderLahdRecordsTrigger(summary) {
        const apn = normalizeNullableString(summary?.apn);
        if (!apn) return "";

        const address = normalizeNullableString(summary?.address) || "";

        return `
            <button
                type="button"
                class="lahd-records-trigger"
                data-lahd-records-trigger="true"
                data-lahd-apn="${escapeHtml(apn)}"
                data-lahd-address="${escapeHtml(address)}"
                data-lahd-source="listing-popup"
            >
                view records
            </button>
        `;
    }

    /**
     * Build the compact Housing Department summary shown in listing popups.
     *
     * @param {unknown} summary Raw `lahd_property_summary` payload.
     * @returns {string} Human-readable housing issue summary.
     */
    function formatLahdIssueSummary(summary) {
        if (!summary || typeof summary !== "object") {
            return "Not available";
        }

        if (summary.data_available === false) {
            return "Not available";
        }

        if (!summary.matched) {
            return "No matching housing cases found";
        }

        const documented = formatWholeNumber(summary.documented_issue_count);
        const unresolved = formatWholeNumber(summary.unresolved_issue_count);
        const latestCaseDate = normalizeNullableString(summary.latest_case_date);
        const latestCaseLabel = latestCaseDate
            ? `; latest ${escapeHtml(latestCaseDate.split("T")[0])}`
            : "";
        const recordsTrigger = renderLahdRecordsTrigger(summary);
        const recordsTriggerLabel = recordsTrigger ? `<br>${recordsTrigger}` : "";

        return `${documented} documented / ${unresolved} unresolved est.${latestCaseLabel}${recordsTriggerLabel}`;
    }

    /**
     * Render the Housing Department issue value for listing popups.
     *
     * @param {Record<string, unknown>} popupData Listing detail payload.
     * @returns {string} HTML value markup, or an empty string.
     */
    function renderLahdValue(popupData) {
        const summary = popupData.lahd_property_summary;
        if (!summary || typeof summary !== "object") return "";
        if (summary.jurisdiction_in_scope === false || summary.data_available === false) {
            return "";
        }
        return formatLahdIssueSummary(summary);
    }

    /**
     * Format LAHD's property-level RSO inventory result without claiming a
     * listing unit is covered when the property has mixed coverage.
     *
     * @param {unknown} summary Raw `rso_property_summary` payload.
     * @returns {string} Human-readable RSO status.
     */
    function formatRsoSummary(summary) {
        if (!summary || typeof summary !== "object" || summary.data_available === false) {
            return "Not available";
        }
        if (!summary.matched) {
            return "Unknown";
        }

        const unitCount = formatWholeNumber(summary.rso_units);
        const unitRange = normalizeNullableString(summary.unit_range);
        const totalUnitsLabel = unitRange ? ` of ${escapeHtml(unitRange)}` : "";
        if (summary.coverage === "all") {
            return `All units covered (${unitCount}${totalUnitsLabel})`;
        }
        return `${unitCount} RSO units${totalUnitsLabel}; verify this unit`;
    }

    /**
     * Render the LA City Rent Stabilization Ordinance value for rental popups.
     *
     * @param {Record<string, unknown>} popupData Listing detail payload.
     * @returns {string} HTML value markup, or an empty string.
     */
    function renderRsoValue(popupData) {
        const summary = popupData.rso_property_summary;
        if (!summary || typeof summary !== "object" || summary.jurisdiction_in_scope === false) {
            return "";
        }
        return formatRsoSummary(summary);
    }

    /**
     * Convert a street address string into title case for popup display.
     *
     * @param {string} value Address string to normalize.
     * @returns {string} Title-cased address string.
     */
    function toTitleCase(value) {
        return String(value).replace(/\w\S*/g, function (txt) {
            return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
        });
    }

    /**
     * Return Dash's requests pathname prefix without a trailing slash.
     *
     * @returns {string} Prefix or an empty string for root apps.
     */
    function getDashPrefix() {
        const cfg = window.__dash_config || {};
        const prefix = cfg.requests_pathname_prefix || cfg.url_base_pathname || "/";
        if (!prefix || prefix === "/") return "";
        return prefix.endsWith("/") ? prefix.slice(0, -1) : prefix;
    }

    /**
     * Build a same-origin URL that respects Dash's pathname prefix.
     *
     * @param {string} path App-relative path.
     * @returns {string} Absolute same-origin URL for `fetch`.
     */
    function buildSameOriginDashUrl(path) {
        const cleanPath = path.startsWith("/") ? path : `/${path}`;
        return `${window.location.origin}${getDashPrefix()}${cleanPath}`;
    }

    /**
     * Resolve the page-specific listing-detail API base path.
     *
     * @returns {string} Lease or buy listing-detail API prefix.
     */
    function getListingDetailApiBasePath() {
        const path = String(window.location?.pathname || "").toLowerCase();
        return path === "/buy" || path.startsWith("/buy")
            ? "/api/buy/listing-details/"
            : "/api/lease/listing-details/";
    }

    /**
     * Fetch listing details for a single popup and cache the in-flight request.
     *
     * @param {string} listingId Listing identifier used by the API.
     * @returns {Promise<Record<string, unknown>>} Promise resolving to popup detail data.
     */
    function fetchListingDetails(listingId) {
        const base = getListingDetailApiBasePath();
        const id = normalizeListingId(listingId);
        const cacheKey = `${base}::${id}`;

        const cached = listingDetailFetchCache.get(cacheKey);
        if (cached) return cached;

        const url = buildSameOriginDashUrl(`${base}${encodeURIComponent(id)}`);

        const p = fetch(url, {
            method: "GET",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        })
            .then((res) => {
                if (!res.ok) throw new Error(`Listing detail fetch failed (${res.status})`);
                return res.json();
            })
            .catch((err) => {
                listingDetailFetchCache.delete(cacheKey);
                throw err;
            });

        listingDetailFetchCache.set(cacheKey, p);
        return p;
    }

    /** Listing hosts we can name, so the link says where it goes. */
    const LISTING_HOST_NAMES = {
        "theagencyre.com": "The Agency",
        "bhhscalifornia.com": "BHHS California",
    };

    /**
     * Human name for a listing host, falling back to its bare domain.
     *
     * @param {string} url Listing detail URL.
     * @returns {string} Display name for the host.
     */
    function listingHostName(url) {
        try {
            const host = new URL(url).hostname.toLowerCase().replace(/^www\./, "");
            return LISTING_HOST_NAMES[host] || host;
        } catch (error) {
            return "the listing site";
        }
    }

    /**
     * Build a listing URL from an MLS number alone.
     *
     * theagencyre.com resolves any `/<segment>/clr/<mls>/<slug>` URL to the
     * canonical listing page, so neither the property type nor the address slug
     * has to be right. Measured: this recovers nothing for listings with no
     * stored URL (0 of 20 sampled returned 200, the rest are genuinely not
     * published there), so it is a last resort behind both the stored URL and
     * the phone number, used only where the popup would otherwise offer nothing.
     *
     * @param {unknown} mlsNumber Listing MLS number.
     * @returns {string|null} Constructed lookup URL, or `null` without an MLS.
     */
    function buildListingUrlFromMls(mlsNumber) {
        const id = normalizeListingId(mlsNumber).toLowerCase();
        if (!id) return null;
        return `https://www.theagencyre.com/listing/clr/${encodeURIComponent(id)}/x`;
    }

    /**
     * Format a phone number as (xxx) xxx-xxxx when it has ten digits.
     *
     * The feed mixes "(626) 862-4732" and "310-577-5300", so normalize rather
     * than print whichever shape the source happened to use.
     *
     * @param {unknown} value Raw phone value.
     * @returns {string|null} Display phone number, or `null` when unusable.
     */
    function formatPhone(value) {
        const raw = normalizeNullableString(value);
        if (!raw) return null;
        const digits = raw.replace(/\D/g, "").replace(/^1(?=\d{10}$)/, "");
        if (digits.length !== 10) return raw;
        return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    }

    /**
     * Render the "where do I go next" line that sits under the address.
     *
     * Around one listing in five is not published on either host. Those used to
     * show nothing actionable at all, so the fallback promotes the listing
     * office phone number instead of hiding it in More details.
     *
     * @param {Record<string, unknown>} popupData Listing detail payload.
     * @returns {string} HTML string for the source line.
     */
    function renderListingSource(popupData) {
        const listingUrl = normalizeNullableString(popupData.listing_url);
        if (listingUrl) {
            return `
                <div class="listing-popup__source">
                    <a class="plausible-listing-link" href="${escapeHtml(listingUrl)}" target="_blank" referrerPolicy="noreferrer">
                        View on ${escapeHtml(listingHostName(listingUrl))}
                    </a>
                </div>
            `;
        }

        const phone = formatPhone(popupData.phone_number);
        if (phone) {
            return `
                <div class="listing-popup__source listing-popup__source--offline">
                    <span>Not listed online</span>
                    <a href="tel:${escapeHtml(phone.replace(/\D/g, ""))}">${escapeHtml(phone)}</a>
                </div>
            `;
        }

        const lookupUrl = buildListingUrlFromMls(popupData.mls_number);
        if (lookupUrl) {
            return `
                <div class="listing-popup__source listing-popup__source--offline">
                    <span>No listing page or phone</span>
                    <a href="${escapeHtml(lookupUrl)}" target="_blank" rel="noreferrer">Try MLS lookup</a>
                </div>
            `;
        }

        return `
            <div class="listing-popup__source listing-popup__source--offline">
                <span>Not listed online</span>
            </div>
        `;
    }

    /**
     * Render the popup heading, linking the address when a listing URL exists.
     *
     * @param {string} address Display-ready street address.
     * @param {string|null} listingUrl Listing detail URL, if available.
     * @returns {string} HTML string for the popup heading.
     */
    function renderHeader(address, listingUrl) {
        const safeAddress = escapeHtml(address);
        const title = listingUrl
            ? `<a class="plausible-listing-link" href="${escapeHtml(listingUrl)}" referrerPolicy="noreferrer" target="_blank">${safeAddress}</a>`
            : safeAddress;
        return `<h5 class="listing-popup__address">${title}</h5>`;
    }

    /**
     * Google Maps URL for a listing's address.
     *
     * The pano is already embedded above this link, so the link is for going to
     * the place itself: searching the address drops you on the map with the
     * usual directions, satellite and nearby options. Coordinates are the
     * fallback when the address is missing, since they always resolve.
     *
     * @param {Record<string, unknown>} popupData Listing detail payload.
     * @returns {string|null} Google Maps URL, or `null` with nothing to point at.
     */
    function buildGoogleMapsUrl(popupData) {
        const address = normalizeNullableString(popupData?.full_street_address);
        if (address) {
            return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
        }
        const lat = Number(popupData?.latitude);
        const lng = Number(popupData?.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
        return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
    }

    /**
     * Embeddable Street View pano URL for a listing's coordinates.
     *
     * `output=svembed` is Google's long-standing keyless embed endpoint. It
     * redirects to /maps/embed, which sends no X-Frame-Options and no CSP
     * frame-ancestors, so it frames without an API key. It is undocumented
     * though, so the caption keeps a normal link to Google Maps as a way out if
     * the endpoint ever stops framing.
     *
     * @param {Record<string, unknown>} popupData Listing detail payload.
     * @returns {string|null} Embeddable pano URL, or `null` without coordinates.
     */
    function buildStreetViewEmbedUrl(popupData) {
        const lat = Number(popupData?.latitude);
        const lng = Number(popupData?.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
        return `https://maps.google.com/maps?q=&layer=c&cbll=${lat},${lng}&cbp=11,0,0,0,0&output=svembed`;
    }

    /**
     * Render the popup's media slot: the MLS photo when there is one, otherwise
     * a Street View link tile.
     *
     * Roughly one listing in eight arrives without a photo. Those popups used to
     * open with an empty gap above the address, which reads as a broken image
     * rather than a missing one.
     *
     * @param {Record<string, unknown>} popupData Listing detail payload.
     * @returns {string} HTML string for the media slot.
     */
    function renderMedia(popupData) {
        const photoUrl = normalizeNullableString(popupData.mls_photo);
        const listingUrl = normalizeNullableString(popupData.listing_url);

        if (photoUrl) {
            const img = `<img class="listing-popup__photo" src="${escapeHtml(photoUrl)}" alt="Listing photo" loading="lazy">`;
            const inner = listingUrl
                ? `<a class="plausible-listing-link" href="${escapeHtml(listingUrl)}" target="_blank" referrerPolicy="noreferrer">${img}</a>`
                : img;
            return `<div class="listing-popup__media">${inner}</div>`;
        }

        const mapsUrl = buildGoogleMapsUrl(popupData);

        const embedUrl = buildStreetViewEmbedUrl(popupData);
        const address = normalizeNullableString(popupData.full_street_address) || "this listing";

        // Labelled, because a pano of the block is not a photo of the unit and
        // should not be mistaken for one.
        return `
            <div class="listing-popup__media listing-popup__media--streetview">
                <iframe
                    class="listing-popup__streetview-frame"
                    src="${escapeHtml(embedUrl)}"
                    title="Street View near ${escapeHtml(address)}"
                    loading="lazy"
                    referrerpolicy="no-referrer-when-downgrade"
                    allowfullscreen></iframe>
            </div>
            <div class="listing-popup__media-caption">
                No listing photo${mapsUrl
                    ? ` &middot; <a class="listing-popup__streetview" href="${escapeHtml(mapsUrl)}" target="_blank" rel="noreferrer">open in Google Maps</a>`
                    : ""}
            </div>
        `;
    }

    /**
     * Report whether a value carries no information worth a popup row.
     *
     * @param {unknown} value Candidate display value.
     * @returns {boolean} `true` when the value should be omitted.
     */
    function isBlankValue(value) {
        if (value === null || value === undefined) return true;
        const normalized = String(value).trim().toLowerCase();
        return ["", "unknown", "none", "null", "nan", "not available"].includes(normalized);
    }

    /**
     * Render one label/value row from trusted HTML.
     *
     * @param {string} label Row label.
     * @param {string} html Pre-rendered value markup.
     * @param {string} [modifier] Extra class for rows that need a wider value.
     * @returns {string} HTML row, or an empty string when there is no value.
     */
    function rawRow(label, html, modifier) {
        if (!html) return "";
        if (!html.includes("<") && isBlankValue(html)) return "";
        return `
            <div class="listing-popup__row${modifier ? ` ${modifier}` : ""}">
                <dt class="listing-popup__label">${escapeHtml(label)}</dt>
                <dd class="listing-popup__value">${html}</dd>
            </div>
        `;
    }

    /**
     * Render one label/value row, dropping it when the value says nothing.
     *
     * The old popup printed every field it knew about, so a typical listing
     * showed a column of "Unknown" that buried the handful of facts that were
     * actually present.
     *
     * @param {string} label Row label.
     * @param {unknown} value Display value.
     * @returns {string} HTML row, or an empty string when the value is blank.
     */
    function row(label, value) {
        if (isBlankValue(value)) return "";
        return rawRow(label, escapeHtml(value));
    }

    /**
     * Render one figure in the key-stats strip.
     *
     * @param {unknown} value Figure to display.
     * @param {string} label Caption under the figure.
     * @returns {string} HTML stat cell, or an empty string when blank.
     */
    function stat(value, label) {
        if (isBlankValue(value)) return "";
        return `
            <div class="listing-popup__stat">
                <span class="listing-popup__stat-value">${escapeHtml(value)}</span>
                <span class="listing-popup__stat-label">${escapeHtml(label)}</span>
            </div>
        `;
    }

    /**
     * Wrap the populated stat cells in the strip, or render nothing.
     *
     * @param {string[]} cells Rendered stat cells.
     * @returns {string} HTML stats strip.
     */
    function renderStats(cells) {
        const html = cells.join("");
        return html ? `<div class="listing-popup__stats">${html}</div>` : "";
    }

    /**
     * Collapse the rarely-populated fields behind a disclosure.
     *
     * @param {string[]} rows Rendered rows.
     * @returns {string} HTML `<details>` block, or an empty string.
     */
    function renderMoreDetails(rows) {
        const html = rows.join("");
        if (!html) return "";
        return `
            <details class="listing-popup__more">
                <summary class="listing-popup__more-summary">More details</summary>
                <dl class="listing-popup__rows">${html}</dl>
            </details>
        `;
    }

    /**
     * Format bedroom and bathroom counts as a single stat figure.
     *
     * @param {Record<string, unknown>} popupData Listing detail payload.
     * @returns {string} Combined bed/bath figure, or an empty string.
     */
    function formatBedBath(popupData) {
        const bedrooms = stripTrailingPointZero(popupData.bedrooms);
        const bathrooms = stripTrailingPointZero(popupData.total_bathrooms);
        if (isBlankValue(bedrooms) && isBlankValue(bathrooms)) return "";
        const bd = isBlankValue(bedrooms) ? "?" : bedrooms;
        const ba = isBlankValue(bathrooms) ? "?" : bathrooms;
        return `${bd} / ${ba}`;
    }

    /**
     * Format square footage as a stat figure.
     *
     * @param {unknown} value Raw square footage.
     * @returns {string} Localized figure, or an empty string.
     */
    function formatSqft(value) {
        const n = Number(value);
        if (!Number.isFinite(n) || n <= 0) return "";
        return n.toLocaleString("en-US");
    }

    /**
     * Format a date-like value as `YYYY-MM-DD`.
     *
     * @param {unknown} dateString Date value pulled from the listing payload.
     * @returns {string} ISO-style date string or `"Unknown"`.
     */
    function formatDate(dateString) {
        if (!dateString) return "Unknown";
        const date = new Date(dateString);
        if (Number.isNaN(date.getTime())) {
            return String(dateString).split("T")[0] || "Unknown";
        }
        return date.toISOString().split("T")[0];
    }

    /**
     * Render the report-listing footer link for a popup.
     *
     * @param {string} listingId Listing identifier / MLS number.
     * @returns {string} HTML string for the report link.
     */
    function renderReportLink(listingId) {
        const payload = encodeURIComponent(JSON.stringify({ mls_number: listingId }));
        return `
            <div class="listing-popup__footer">
                <a class="listing-popup__report" href="#" title="Report this listing" onclick='reportListing(decodeURIComponent("${payload}"))'>
                    <i class="fa-solid fa-flag"></i>
                    <span>Report listing</span>
                </a>
            </div>
        `;
    }

    /**
     * Build the lease-page popup body for a single listing.
     *
     * Ordered by what a renter decides on: the photo, the address, the four
     * figures that rule a listing in or out, then the qualifying facts. Anything
     * mostly blank across the dataset sits behind "More details".
     *
     * @param {Record<string, unknown>} popupData Listing properties shown in the popup.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function generateLeasePopupContent(popupData) {
        const listingUrl = normalizeNullableString(popupData.listing_url);
        const address = toTitleCase(
            stripTrailingPointZero(normalizeNullableString(popupData.full_street_address))
                || "Unknown Address",
        );
        const ispHtml = window.larentals?.isp?.renderIspOptionsPlaceholderHtml(popupData.mls_number) ?? "";

        const primaryRows = [
            rawRow("Rent control", renderRsoValue(popupData)),
            rawRow("Housing Dept. issues", renderLahdValue(popupData)),
            row("Security deposit", formatCurrency(popupData.security_deposit)),
            row("Pets", popupData.pet_policy),
            row("Laundry", popupData.laundry),
            row("Parking", popupData.parking_spaces),
            row("Furnished", popupData.furnished),
            row("Listed", formatDate(popupData.listed_date)),
        ];

        const moreRows = [
            row("Rental terms", popupData.terms),
            row("Property type", popupData.subtype),
            row("Year built", popupData.year_built),
            row("Pet deposit", formatCurrency(popupData.pet_deposit)),
            row("Key deposit", formatCurrency(popupData.key_deposit)),
            row("Other deposit", formatCurrency(popupData.other_deposit)),
            row("Listing ID (MLS#)", stripTrailingPointZero(popupData.mls_number)),
            rawRow("ISP options", ispHtml, "listing-popup__row--stacked"),
        ];

        return `
            <div class="listing-popup">
                ${renderMedia(popupData)}
                ${renderHeader(address, listingUrl)}
                ${renderListingSource(popupData)}
                ${renderStats([
                    stat(formatCurrency(popupData.list_price), "per month"),
                    stat(formatBedBath(popupData), "bed / bath"),
                    stat(formatSqft(popupData.sqft), "sq ft"),
                    stat(popupData.ppsqft ? formatCurrency(popupData.ppsqft) : "", "per sq ft"),
                ])}
                <dl class="listing-popup__rows">${primaryRows.join("")}</dl>
                ${renderMoreDetails(moreRows)}
                ${renderReportLink(normalizeListingId(popupData.mls_number))}
            </div>
        `;
    }

    /**
     * Build the buy-page popup body for a single listing.
     *
     * @param {Record<string, unknown>} popupData Listing properties shown in the popup.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function generateBuyPopupContent(popupData) {
        const listingUrl = normalizeNullableString(popupData.listing_url);
        const address = toTitleCase(
            stripTrailingPointZero(normalizeNullableString(popupData.full_street_address))
                || "Unknown Address",
        );
        const subtype = normalizeNullableString(popupData.subtype);
        const isSfr = Boolean(subtype)
            && (subtype.includes("SFR") || subtype.includes("Single Family Residence"));
        const lotSizeDisplay = formatLotSize(popupData.lot_size);
        const ispHtml = window.larentals?.isp?.renderIspOptionsPlaceholderHtml(popupData.mls_number) ?? "";

        const primaryRows = [
            rawRow("Rent control", renderRsoValue(popupData)),
            rawRow("Housing Dept. issues", renderLahdValue(popupData)),
            row("HOA fee", formatCurrency(popupData.hoa_fee)),
            row("HOA frequency", popupData.hoa_fee_frequency),
            row("Lot size", lotSizeDisplay ? `${lotSizeDisplay} sq. ft` : ""),
            isSfr ? "" : row("Parking", popupData.garage_spaces),
            row("School district", popupData.school_district_name),
            row("Nearest high school", formatMiles(popupData.nearest_high_school_mi)),
            row("Listed", formatDate(popupData.listed_date)),
        ];

        const moreRows = [
            row("Property type", subtype),
            row("Year built", popupData.year_built),
            row("Listing ID (MLS#)", stripTrailingPointZero(popupData.mls_number)),
            rawRow("ISP options", ispHtml, "listing-popup__row--stacked"),
        ];

        return `
            <div class="listing-popup">
                ${renderMedia(popupData)}
                ${renderHeader(address, listingUrl)}
                ${renderListingSource(popupData)}
                ${renderStats([
                    stat(formatCurrency(popupData.list_price), "list price"),
                    stat(formatBedBath(popupData), "bed / bath"),
                    stat(formatSqft(popupData.sqft), "sq ft"),
                    stat(popupData.ppsqft ? formatCurrency(popupData.ppsqft) : "", "per sq ft"),
                ])}
                <dl class="listing-popup__rows">${primaryRows.join("")}</dl>
                ${renderMoreDetails(moreRows)}
                ${renderReportLink(normalizeListingId(popupData.mls_number))}
            </div>
        `;
    }

    /**
     * Render a lightweight loading shell while popup details are fetched.
     *
     * @param {Record<string, unknown>} summaryData Initial marker data.
     * @returns {string} HTML string for the loading state.
     */
    function renderPopupLoadingContent(summaryData) {
        const listingId = normalizeListingId(summaryData.mls_number) || "Unknown";
        const subtype = escapeHtml(summaryData.subtype || "Listing");
        const price = escapeHtml(formatCurrency(summaryData.list_price));

        return `
            <div style="min-width: 220px; padding: 6px 2px;">
                <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px;">${subtype}</div>
                <div style="font-size: 13px; color: #555; margin-bottom: 4px;">MLS ${escapeHtml(listingId)}</div>
                <div style="font-size: 13px; color: #111; margin-bottom: 10px;">${price}</div>
                <div style="font-size: 13px; color: #666;">Loading listing details...</div>
            </div>
        `;
    }

    /**
     * Render a fallback error state when popup details fail to load.
     *
     * @param {Record<string, unknown>} summaryData Initial marker data.
     * @returns {string} HTML string for the error state.
     */
    function renderPopupErrorContent(summaryData) {
        const listingId = normalizeListingId(summaryData.mls_number) || "Unknown";
        return `
            <div style="min-width: 220px; padding: 6px 2px;">
                <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px;">Listing ${escapeHtml(listingId)}</div>
                <div style="font-size: 13px; color: #666;">Could not load listing details right now.</div>
                ${renderReportLink(listingId)}
            </div>
        `;
    }

    /**
     * Compute the responsive popup sizing constraints for a map layer.
     *
     * @param {PopupLayer} layer Leaflet layer bound to the popup.
     * @returns {Record<string, unknown>} Leaflet popup options.
     */
    function buildPopupOptions(layer) {
        const isMobile = L.Browser.mobile || window.innerWidth < 768;
        const mapEl = layer?._map?.getContainer?.() ?? null;
        const rect = mapEl?.getBoundingClientRect?.() ?? null;

        const availW = Math.floor(Math.min(window.innerWidth, rect?.width ?? window.innerWidth));
        const availH = Math.floor(Math.min(window.innerHeight, rect?.height ?? window.innerHeight));

        const padding = isMobile ? 24 : 48;
        const leaseLikeMaxWidthCap = isMobile ? 225 : 350;
        const leaseLikeMaxHeightCap = isMobile ? 405 : 650;

        return {
            maxWidth: Math.max(200, Math.min(leaseLikeMaxWidthCap, availW - padding)),
            maxHeight: Math.max(220, Math.min(leaseLikeMaxHeightCap, availH - padding)),
            keepInView: false,
            autoPanPadding: [10, 10],
            closeButton: true,
            className: "responsive-popup",
        };
    }

    /**
     * Update the popup content and hydrate ISP placeholder content if present.
     *
     * @param {PopupLayer} layer Leaflet layer whose popup should be updated.
     * @param {string} content HTML content for the popup.
     * @returns {void}
     */
    function setPopupContent(layer, content) {
        const popup = layer.getPopup?.();
        if (!popup || typeof popup.setContent !== "function") return;

        popup.setContent(content);

        const popupEl = popup.getElement?.();
        if (!popupEl) return;

        const ispApi = window.larentals?.isp;
        if (!ispApi) return;

        ispApi.hydrateIspOptionsInPopup(popupEl);
    }

    window.dash_props = Object.assign({}, window.dash_props, {
        module: Object.assign({}, window.dash_props && window.dash_props.module, {
            /**
             * Build and bind the main property popup for a GeoJSON listing feature.
             *
             * @param {PopupFeature} feature GeoJSON feature emitted by Dash Leaflet.
             * @param {PopupLayer} layer Leaflet layer receiving the popup binding.
             * @returns {void} Does not return a value; mutates the supplied layer.
             */
            on_each_feature: function (feature, layer) {
                if (!feature.properties) {
                    console.warn("Feature properties are missing.");
                    return;
                }

                const summaryData = feature.properties;
                const path = String(window.location?.pathname || "").toLowerCase();
                const isBuyPage = path === "/buy" || path.startsWith("/buy");
                const listingId = normalizeListingId(summaryData.mls_number);
                let openRequestSeq = 0;

                layer.bindPopup(renderPopupLoadingContent(summaryData), buildPopupOptions(layer));

                layer.on("popupopen", function handlePopupOpen() {
                    openRequestSeq += 1;
                    const requestSeq = openRequestSeq;

                    window.larentals?.analytics?.trackListingOpened();

                    setPopupContent(layer, renderPopupLoadingContent(summaryData));

                    if (!listingId) {
                        setPopupContent(layer, renderPopupErrorContent(summaryData));
                        return;
                    }

                    fetchListingDetails(listingId)
                        .then((detailData) => {
                            if (requestSeq !== openRequestSeq) return;

                            const popupData = Object.assign({}, summaryData, detailData || {});
                            const popupContent = isBuyPage
                                ? generateBuyPopupContent(popupData)
                                : generateLeasePopupContent(popupData);

                            setPopupContent(layer, popupContent);
                        })
                        .catch((error) => {
                            if (requestSeq !== openRequestSeq) return;
                            console.error("Failed to load popup details for listing", listingId, error);
                            setPopupContent(layer, renderPopupErrorContent(summaryData));
                        });
                });
            },
        }),
    });
})();
