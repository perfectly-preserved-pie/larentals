(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const popupUtils = popupApi && popupApi.utils;
    const registerPopupBuilder = popupRuntime && popupRuntime.registerPopupBuilder;
    const toDisplayTitleCase = popupUtils && popupUtils.toDisplayTitleCase;

    if (!popupUtils || typeof registerPopupBuilder !== "function") {
        console.error("Additional layer popup utils did not load before the LAHD popup builder.");
        return;
    }

    const escapeHtml = popupUtils.escapeHtml;
    const formatPopupDate = popupUtils.formatPopupDate;
    const renderPopupCard = popupUtils.renderPopupCard;

    /**
     * @typedef {{
     *   address?: unknown,
     *   apn?: unknown,
     *   problem_score?: unknown,
     *   documented_issue_count?: unknown,
     *   unresolved_issue_count?: unknown,
     *   investigation_case_count?: unknown,
     *   open_case_count?: unknown,
     *   violations_cited?: unknown,
     *   unresolved_violation_count?: unknown,
     *   violation_row_count?: unknown,
     *   closed_case_count?: unknown,
     *   violations_cleared?: unknown,
     *   first_case_date?: unknown,
     *   latest_case_date?: unknown,
     * }} LahdPropertyProperties
     */

    /**
     * Format a numeric value as a localized integer.
     *
     * @param {unknown} value Raw numeric value.
     * @returns {string} Localized integer string or `N/A`.
     */
    function formatWholeNumber(value) {
        const numberValue = Number(value);
        if (!Number.isFinite(numberValue)) {
            return "N/A";
        }

        return escapeHtml(Math.round(numberValue).toLocaleString("en-US"));
    }

    /**
     * Render the Dash drawer trigger for a property APN.
     *
     * @param {LahdPropertyProperties} properties Feature properties for the hotspot.
     * @returns {string} HTML drawer trigger or `N/A`.
     */
    function renderLahdRecordsTrigger(properties) {
        const apn = String(properties.apn || "").trim();
        if (!apn) {
            return "N/A";
        }

        const address = String(properties.address || "").trim();
        return `
            <button
                type="button"
                class="lahd-records-trigger"
                data-lahd-records-trigger="true"
                data-lahd-apn="${escapeHtml(apn)}"
                data-lahd-address="${escapeHtml(address)}"
                data-lahd-source="lahd-heatmap-popup"
            >
                View records
            </button>
        `;
    }

    /**
     * Build a compact count pair for popup display.
     *
     * @param {unknown} primary Primary count.
     * @param {string} primaryLabel Label for the primary count.
     * @param {unknown} secondary Secondary count.
     * @param {string} secondaryLabel Label for the secondary count.
     * @returns {string} Escaped count-pair label.
     */
    function formatCountPair(primary, primaryLabel, secondary, secondaryLabel) {
        return [
            formatWholeNumber(primary),
            " ",
            escapeHtml(primaryLabel),
            " / ",
            formatWholeNumber(secondary),
            " ",
            escapeHtml(secondaryLabel),
        ].join("");
    }

    /**
     * Build the ordered rows rendered in a Housing Department property popup.
     *
     * @param {LahdPropertyProperties} properties Feature properties for the hotspot.
     * @returns {{label: string, value: string}[]} Popup rows for the feature.
     */
    function buildLahdPropertyRows(properties) {
        return [
            {
                label: "Documented Issues",
                value: formatWholeNumber(properties.documented_issue_count),
            },
            {
                label: "Unresolved Estimate",
                value: formatWholeNumber(properties.unresolved_issue_count),
            },
            {
                label: "Investigation Cases",
                value: formatCountPair(
                    properties.investigation_case_count,
                    "total",
                    properties.open_case_count,
                    "open"
                ),
            },
            {
                label: "Code Violations",
                value: formatCountPair(
                    properties.violations_cited,
                    "cited",
                    properties.unresolved_violation_count,
                    "uncleared"
                ),
            },
            {
                label: "Violation Rows",
                value: formatWholeNumber(properties.violation_row_count),
            },
            {
                label: "APN",
                value: properties.apn ? escapeHtml(properties.apn) : "N/A",
            },
            {
                label: "Source Records",
                value: renderLahdRecordsTrigger(properties),
            },
            {
                label: "First Case",
                value: formatPopupDate(properties.first_case_date),
            },
            {
                label: "Latest Case",
                value: formatPopupDate(properties.latest_case_date),
            },
        ];
    }

    /**
     * Build the popup title for an LAHD hotspot.
     *
     * @param {LahdPropertyProperties} properties Feature properties for the hotspot.
     * @returns {string} Popup title.
     */
    function buildLahdPropertyTitle(properties) {
        const address = String(properties.address || "").trim();
        if (address) {
            return toDisplayTitleCase(address);
        }

        const issueCount = Number(properties.documented_issue_count);
        if (Number.isFinite(issueCount) && issueCount > 0) {
            return `${Math.round(issueCount).toLocaleString("en-US")} Housing Issues`;
        }

        return "Housing Department Property";
    }

    /**
     * Build the complete Housing Department property popup markup.
     *
     * @param {LahdPropertyProperties} properties Feature properties for the hotspot.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildLahdPropertyPopupContent(properties) {
        const banner = [
            '<div class="additional-layer-popup__banner">',
            "Counts combine Housing Department investigation/enforcement cases and code-violation citations.",
            "</div>",
        ].join("");

        return renderPopupCard({
            title: buildLahdPropertyTitle(properties),
            rows: buildLahdPropertyRows(properties),
            banner: banner,
        });
    }

    registerPopupBuilder("buildLahdPropertyPopupContent", buildLahdPropertyPopupContent);
})();
