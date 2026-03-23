(function() {
    "use strict";

    /**
     * @typedef {{ label: string, value: string }} PopupRow
     */

    /**
     * Check whether a popup value should be treated as blank.
     *
     * @param {unknown} value Raw property value.
     * @returns {boolean} `true` when the value is empty or null-like.
     */
    function isBlankValue(value) {
        if (value === null || value === undefined) {
            return true;
        }

        if (typeof value === "string") {
            const normalized = value.trim().toLowerCase();
            return normalized === "" || normalized === "null" || normalized === "none" || normalized === "nan";
        }

        return false;
    }

    /**
     * Convert a value into a trimmed string when it is usable.
     *
     * @param {unknown} value Raw property value.
     * @returns {string|null} Trimmed string or `null`.
     */
    function getTrimmedString(value) {
        if (isBlankValue(value)) {
            return null;
        }

        return String(value).trim();
    }

    /**
     * Escape text for safe HTML interpolation inside popup content.
     *
     * @param {unknown} value Raw text value to escape.
     * @returns {string} HTML-safe string.
     */
    function escapeHtml(value) {
        const stringValue = value === null || value === undefined ? "" : String(value);
        return stringValue
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    /**
     * Format a plain text value for popup display.
     *
     * @param {unknown} value Raw property value.
     * @returns {string} Escaped text or `N/A`.
     */
    function formatTextValue(value) {
        const normalized = getTrimmedString(value);
        return normalized ? escapeHtml(normalized) : "N/A";
    }

    /**
     * Convert a military-style time value into a 12-hour display string.
     *
     * @param {unknown} time Raw time value, typically in `HHMM` form.
     * @returns {string} Formatted 12-hour time string or `N/A`.
     */
    function militaryToStandard(time) {
        const rawTime = getTrimmedString(time);
        if (!rawTime) {
            return "N/A";
        }

        const digitsOnly = rawTime.replace(/[^\d]/g, "");
        if (!digitsOnly) {
            return "N/A";
        }

        const normalized = digitsOnly.padStart(4, "0").slice(-4);
        const hours = parseInt(normalized.substring(0, 2), 10);
        const minutes = parseInt(normalized.substring(2, 4), 10);

        if (!Number.isInteger(hours) || !Number.isInteger(minutes) || hours > 23 || minutes > 59) {
            return "N/A";
        }

        const suffix = hours >= 12 ? "PM" : "AM";
        const displayHours = ((hours + 11) % 12) + 1;
        const displayMinutes = minutes < 10 ? `0${minutes}` : String(minutes);

        return `${displayHours}:${displayMinutes} ${suffix}`;
    }

    /**
     * Format a popup date value for display.
     *
     * @param {unknown} value Raw date-like value from a feature property.
     * @returns {string} Escaped date string, or `N/A` when the value is blank.
     */
    function formatPopupDate(value) {
        const normalized = getTrimmedString(value);
        if (!normalized) {
            return "N/A";
        }

        if (normalized.includes("T")) {
            return escapeHtml(normalized.split("T")[0]);
        }

        return escapeHtml(normalized);
    }

    /**
     * Join address fragments while filtering blank values.
     *
     * @param {unknown[]} parts Address fragments in display order.
     * @returns {string} Comma-separated address string.
     */
    function joinAddressParts(parts) {
        return parts
            .map(getTrimmedString)
            .filter(Boolean)
            .join(", ");
    }

    /**
     * Normalize text into title case when the source is all upper or all lower case.
     *
     * @param {unknown} value Raw text value to normalize.
     * @returns {string|null} Title-cased string, or `null` when blank.
     */
    function toDisplayTitleCase(value) {
        const normalized = getTrimmedString(value);
        if (!normalized) {
            return null;
        }

        const collapsedWhitespace = normalized.replace(/\s+/g, " ");
        const needsNormalization =
            collapsedWhitespace === collapsedWhitespace.toUpperCase() ||
            collapsedWhitespace === collapsedWhitespace.toLowerCase();

        if (!needsNormalization) {
            return collapsedWhitespace;
        }

        return collapsedWhitespace
            .toLowerCase()
            .replace(/\b([a-z])([a-z']*)/g, function(match, firstLetter, restOfWord) {
                return firstLetter.toUpperCase() + restOfWord;
            });
    }

    /**
     * Build a safe external link for popup display.
     *
     * @param {unknown} url URL value to render.
     * @param {unknown} label Link text.
     * @returns {string} HTML anchor tag or `N/A`.
     */
    function buildExternalLink(url, label) {
        const normalizedUrl = getTrimmedString(url);
        if (!normalizedUrl) {
            return "N/A";
        }

        const safeUrl = escapeHtml(normalizedUrl);
        const normalizedLabel = getTrimmedString(label) || normalizedUrl;

        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(normalizedLabel)}</a>`;
    }

    /**
     * Render the shared popup row layout.
     *
     * @param {PopupRow[]} rows Popup rows to render.
     * @returns {string} HTML string for the popup rows.
     */
    function renderPopupRows(rows) {
        const filteredRows = (rows || []).filter(Boolean);
        if (!filteredRows.length) {
            return `
                <div class="additional-layer-popup__empty">
                    No additional details available.
                </div>
            `;
        }

        return filteredRows
            .map(function(row) {
                return `
                    <div class="additional-layer-popup__row">
                        <div class="additional-layer-popup__label">${escapeHtml(row.label)}</div>
                        <div class="additional-layer-popup__value">
                            ${row.value}
                        </div>
                    </div>
                `;
            })
            .join("");
    }

    /**
     * Render the shared popup card shell used by additional layers.
     *
     * @param {{
     *   title: unknown,
     *   rows: PopupRow[],
     *   banner?: string,
     *   sizeVariant?: "standard"|"wide",
     *   heightVariant?: "standard"|"tall",
     * }} config Popup shell configuration.
     * @returns {string} HTML string bound to a Leaflet popup.
     */
    function renderPopupCard(config) {
        const title = getTrimmedString(config.title) || "Details";
        const banner = typeof config.banner === "string" ? config.banner : "";
        const sizeVariantClass = config.sizeVariant === "wide"
            ? " additional-layer-popup--wide"
            : "";
        const heightVariantClass = config.heightVariant === "tall"
            ? " additional-layer-popup__body--tall"
            : "";

        return `
            <div class="additional-layer-popup${sizeVariantClass}">
                <div class="additional-layer-popup__header">
                    <h5 class="additional-layer-popup__title">${escapeHtml(title)}</h5>
                </div>
                <div class="additional-layer-popup__body${heightVariantClass}">
                    ${banner}
                    ${renderPopupRows(config.rows)}
                </div>
            </div>
        `;
    }

    window.additionalLayerPopups = Object.assign({}, window.additionalLayerPopups, {
        utils: Object.assign({}, window.additionalLayerPopups && window.additionalLayerPopups.utils, {
            buildExternalLink: buildExternalLink,
            escapeHtml: escapeHtml,
            formatPopupDate: formatPopupDate,
            formatTextValue: formatTextValue,
            getTrimmedString: getTrimmedString,
            isBlankValue: isBlankValue,
            joinAddressParts: joinAddressParts,
            militaryToStandard: militaryToStandard,
            renderPopupCard: renderPopupCard,
            renderPopupRows: renderPopupRows,
            toDisplayTitleCase: toDisplayTitleCase,
        }),
    });
})();
