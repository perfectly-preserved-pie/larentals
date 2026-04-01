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

    /**
     * Render the popup title block, linking the address when a listing URL exists.
     *
     * @param {string|number} address Display-ready street address.
     * @param {string|null} listingUrl Listing detail URL, if available.
     * @returns {string} HTML string for the popup heading.
     */
    function getListingUrlBlock(address, listingUrl) {
        if (!listingUrl) {
            return `
                <div style="text-align: center;">
                    <h5>${address}</h5>
                </div>
            `;
        }

        return `
            <div style="text-align: center;">
                <h5><a href="${listingUrl}" referrerPolicy="noreferrer" target="_blank">${address}</a></h5>
            </div>
        `;
    }

    /**
     * Render the property photo row, optionally wrapping the image in the listing URL.
     *
     * @param {string|null} photoUrl Image URL for the listing.
     * @param {string|null} listingUrl Listing detail URL, if available.
     * @returns {string} HTML string for the image row.
     */
    function buildImageRow(photoUrl, listingUrl) {
        if (!photoUrl) return "";

        const imageTag = `<img src="${photoUrl}" alt="Property Image" style="width:100%;height:auto;">`;
        if (listingUrl) {
            return `
                <div style="position: relative;">
                    <a href="${listingUrl}" target="_blank" referrerPolicy="noreferrer">
                        ${imageTag}
                    </a>
                </div>
            `;
        }

        return `
            <div style="position: relative;">
                ${imageTag}
            </div>
        `;
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
            <div style="text-align: center; margin-top: 10px;">
                <a href="#" title="Report Listing" onclick='reportListing(decodeURIComponent("${payload}"))' style="text-decoration: none; color: red;">
                    <i class="fa-solid fa-flag" style="font-size:1.25em; vertical-align: middle;"></i>
                    <span style="vertical-align: middle; margin-left: 5px;">Report Listing</span>
                </a>
            </div>
        `;
    }

    /**
     * Render a small commute verification pill when commute metadata is present.
     *
     * @param {Record<string, unknown>} popupData Listing properties shown in the popup.
     * @returns {string} HTML string for the commute status block.
     */
    function renderCommuteStatusBlock(popupData) {
        const label = normalizeNullableString(popupData.commute_status_text);
        if (!label) return "";

        const matchState = normalizeNullableString(popupData.commute_match_state) || "";
        let background = "#eef2ff";
        let color = "#334155";

        if (matchState === "verified_match") {
            background = "#e8f5e9";
            color = "#1b5e20";
        } else if (matchState === "rough_match") {
            background = "#fff8e1";
            color = "#8a5a00";
        }

        return `
            <div style="margin-top: 10px; padding: 8px 10px; border-radius: 10px; background: ${background}; color: ${color}; font-size: 12px; font-weight: 600;">
                ${escapeHtml(label)}
            </div>
        `;
    }

    /**
     * Build the lease-page popup body for a single listing.
     *
     * @param {Record<string, unknown>} popupData Listing properties shown in the popup.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function generateLeasePopupContent(popupData) {
        const listingUrl = normalizeNullableString(popupData.listing_url);
        const mlsPhoto = normalizeNullableString(popupData.mls_photo);
        const fullStreetAddressRaw = stripTrailingPointZero(
            normalizeNullableString(popupData.full_street_address),
        ) || "Unknown Address";
        const fullStreetAddress = toTitleCase(fullStreetAddressRaw);
        const listingUrlBlock = getListingUrlBlock(fullStreetAddress, listingUrl);
        const imageRow = buildImageRow(mlsPhoto, listingUrl);
        const phoneNumber = normalizeNullableString(popupData.phone_number);
        const phoneNumberBlock = phoneNumber
            ? `<a href="tel:${phoneNumber}">${phoneNumber}</a>`
            : "Unknown";
        const subtype = (popupData?.subtype ?? "Unknown").toString();
        const mlsNumberDisplay = stripTrailingPointZero(popupData.mls_number);
        const reportLink = renderReportLink(normalizeListingId(popupData.mls_number));
        const commuteStatusBlock = renderCommuteStatusBlock(popupData);

        return `
            <div>
                ${imageRow}
                ${listingUrlBlock}
                ${commuteStatusBlock}
                <div class="property-card" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Listed Date</span>
                        <span class="value">${formatDate(popupData.listed_date)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Listing ID (MLS#)</span>
                        <span class="value">${mlsNumberDisplay}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">List Office Phone</span>
                        <span class="value">${phoneNumberBlock}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Rental Price</span>
                        <span class="value">${formatCurrency(popupData.list_price)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Security Deposit</span>
                        <span class="value">${formatCurrency(popupData.security_deposit)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Pet Deposit</span>
                        <span class="value">${formatCurrency(popupData.pet_deposit)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Key Deposit</span>
                        <span class="value">${formatCurrency(popupData.key_deposit)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Other Deposit</span>
                        <span class="value">${formatCurrency(popupData.other_deposit)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Square Feet</span>
                        <span class="value">${popupData.sqft ? `${Number(popupData.sqft).toLocaleString()} sq. ft` : "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Price Per Square Foot</span>
                        <span class="value">${popupData.ppsqft ? `$${Number(popupData.ppsqft).toLocaleString()}` : "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Bedrooms/Bathrooms</span>
                        <span class="value">${popupData.bedrooms}/${popupData.total_bathrooms}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Parking Spaces</span>
                        <span class="value">${popupData.parking_spaces || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Pets Allowed?</span>
                        <span class="value">${popupData.pet_policy || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Furnished?</span>
                        <span class="value">${popupData.furnished || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Laundry Features</span>
                        <span class="value" style="white-space: normal; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word;">
                            ${popupData.laundry || "Unknown"}
                        </span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Year Built</span>
                        <span class="value">${popupData.year_built || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Rental Terms</span>
                        <span class="value">${popupData.terms || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Physical Sub Type</span>
                        <span class="value">${subtype || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display:flex; justify-content:space-between; align-items:flex-start; padding:8px; border-bottom:1px solid #ddd; gap:12px;">
                        <span class="label" style="font-weight:bold;">ISP Options</span>
                        <div class="value" style="text-align:right;">
                            ${window.larentals?.isp?.renderIspOptionsPlaceholderHtml(popupData.mls_number) ?? ""}
                        </div>
                    </div>
                </div>
                ${reportLink}
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
        const mlsPhoto = normalizeNullableString(popupData.mls_photo);
        const fullStreetAddressRaw = stripTrailingPointZero(
            normalizeNullableString(popupData.full_street_address),
        ) || "Unknown Address";
        const fullStreetAddress = toTitleCase(fullStreetAddressRaw);
        const listingUrlBlock = getListingUrlBlock(fullStreetAddress, listingUrl);
        const imageRow = buildImageRow(mlsPhoto, listingUrl);
        const lotSizeDisplay = formatLotSize(popupData.lot_size);
        const mlsNumberDisplay = stripTrailingPointZero(popupData.mls_number);
        const subtype = (popupData?.subtype ?? "Unknown").toString();
        const isSfr = subtype.includes("SFR") || subtype.includes("Single Family Residence");
        const reportLink = renderReportLink(normalizeListingId(popupData.mls_number));
        const commuteStatusBlock = renderCommuteStatusBlock(popupData);

        let parkingContent = "";
        if (!isSfr) {
            parkingContent = `
                <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                    <span class="label" style="font-weight: bold;">Parking Spaces</span>
                    <span class="value">${popupData.garage_spaces || "Unknown"}</span>
                </div>
            `;
        }

        return `
            <div>
                ${imageRow}
                ${listingUrlBlock}
                ${commuteStatusBlock}
                <div class="property-card" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Listed Date</span>
                        <span class="value">${formatDate(popupData.listed_date)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Listing ID (MLS#)</span>
                        <span class="value">${mlsNumberDisplay}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">List Office Phone</span>
                        <span class="value">Unknown</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">List Price</span>
                        <span class="value">${formatCurrency(popupData.list_price)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">HOA Fee</span>
                        <span class="value">${formatCurrency(popupData.hoa_fee)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">HOA Fee Frequency</span>
                        <span class="value">${popupData.hoa_fee_frequency || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Square Feet</span>
                        <span class="value">${popupData.sqft ? `${Number(popupData.sqft).toLocaleString()} sq. ft` : "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Price Per Square Foot</span>
                        <span class="value">${formatCurrency(popupData.ppsqft)}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Lot Size</span>
                        <span class="value">${lotSizeDisplay ? `${lotSizeDisplay} sq. ft` : "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Bedrooms/Bathrooms</span>
                        <span class="value">${popupData.bedrooms}/${popupData.total_bathrooms}</span>
                    </div>
                    ${parkingContent}
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Year Built</span>
                        <span class="value">${popupData.year_built || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                        <span class="label" style="font-weight: bold;">Physical Sub Type</span>
                        <span class="value">${subtype || "Unknown"}</span>
                    </div>
                    <div class="property-row" style="display: flex; justify-content: space-between; align-items: flex-start; padding: 8px; border-bottom: 1px solid #ddd; gap: 12px;">
                        <span class="label" style="font-weight: bold;">ISP Options</span>
                        <div class="value" style="text-align: right;">
                            ${window.larentals?.isp?.renderIspOptionsPlaceholderHtml(popupData.mls_number) ?? ""}
                        </div>
                    </div>
                </div>
                ${reportLink}
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
        const commuteStatusBlock = renderCommuteStatusBlock(summaryData);

        return `
            <div style="min-width: 220px; padding: 6px 2px;">
                <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px;">${subtype}</div>
                <div style="font-size: 13px; color: #555; margin-bottom: 4px;">MLS ${escapeHtml(listingId)}</div>
                <div style="font-size: 13px; color: #111; margin-bottom: 10px;">${price}</div>
                ${commuteStatusBlock}
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
        const commuteStatusBlock = renderCommuteStatusBlock(summaryData);
        return `
            <div style="min-width: 220px; padding: 6px 2px;">
                <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px;">Listing ${escapeHtml(listingId)}</div>
                ${commuteStatusBlock}
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
