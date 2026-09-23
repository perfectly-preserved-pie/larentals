/**
 * Format farmers-market feature properties into popup markup.
 */
(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupUtils = popupApi && popupApi.utils;
    const popupRuntime = popupApi && popupApi.runtime;
    const registerPopupBuilder = popupRuntime && popupRuntime.registerPopupBuilder;

    if (!popupUtils || typeof registerPopupBuilder !== "function") {
        console.error("Additional layer popup utils did not load before the farmers market popup builder.");
        return;
    }

    const buildExternalLink = popupUtils.buildExternalLink;
    const escapeHtml = popupUtils.escapeHtml;
    const getTrimmedString = popupUtils.getTrimmedString;
    const isBlankValue = popupUtils.isBlankValue;
    const joinAddressParts = popupUtils.joinAddressParts;
    const renderPopupCard = popupUtils.renderPopupCard;

    /**
     * Format a farmers market property value for popup display.
     * URL, email, and county fields get appropriate link or Yes/No treatment; other text is escaped.
     *
     * @param {string} key Property key being rendered.
     * @param {unknown} value Raw property value.
     *
     * @returns {string} Escaped HTML string for the property value.
     */
    function formatFarmersMarketValue(key, value) {
        if (isBlankValue(value)) {
            return "N/A";
        }

        const valueAsString = String(value).trim();

        if ((key === "url" || key === "link") && /^https?:\/\//i.test(valueAsString)) {
            return buildExternalLink(valueAsString, valueAsString);
        }

        if (key === "email") {
            const safeEmail = escapeHtml(valueAsString);
            return `<a href="mailto:${safeEmail}">${safeEmail}</a>`;
        }

        if (key === "isCounty") {
            return Number(value) === 1 ? "Yes" : "No";
        }

        return escapeHtml(valueAsString);
    }

    /**
     * Build the formatted address line for a farmers market popup.
     * Street and city/state/ZIP fragments are joined independently so either partial address can display.
     *
     * @param {Record<string, unknown>} properties Feature properties for the farmers market.
     * @returns {string} Escaped address string, or `N/A` when unavailable.
     */
    function buildFarmersMarketAddress(properties) {
        const street = joinAddressParts([properties.addrln1, properties.addrln2]);
        const cityStateZip = joinAddressParts([properties.city, properties.state, properties.zip]);

        if (!street && !cityStateZip) {
            return "N/A";
        }

        if (!street) {
            return escapeHtml(cityStateZip);
        }

        if (!cityStateZip) {
            return escapeHtml(street);
        }

        return escapeHtml(`${street}, ${cityStateZip}`);
    }

    /**
     * Build the website block for a farmers market popup.
     * Duplicate URL and link fields are shown once; distinct sources are listed on separate lines.
     *
     * @param {Record<string, unknown>} properties Feature properties for the farmers market.
     * @returns {string} HTML link block, or `N/A` when no site is available.
     */
    function buildFarmersMarketWebsite(properties) {
        const url = getTrimmedString(properties.url);
        const link = getTrimmedString(properties.link);
        const candidates = [];

        if (url) {
            candidates.push(url);
        }

        if (link && link !== url) {
            candidates.push(link);
        }

        if (!candidates.length) {
            return "N/A";
        }

        return candidates
            .map(function(candidate) {
                return buildExternalLink(candidate, candidate);
            })
            .join("<br>");
    }

    /**
     * Build the ordered rows rendered in a farmers market popup.
     * Hours, website, and county status use shared formatting and link rules.
     *
     * @param {Record<string, unknown>} properties Feature properties for the farmers market.
     * @returns {{ label: string, value: string }[]} Popup rows for the feature.
     */
    function buildFarmersMarketRows(properties) {
        return [
            {
                label: "Address",
                value: buildFarmersMarketAddress(properties),
            },
            {
                label: "Hours",
                value: formatFarmersMarketValue("hours", properties.hours),
            },
            {
                label: "Website",
                value: buildFarmersMarketWebsite(properties),
            },
            {
                label: "County Market",
                value: formatFarmersMarketValue("isCounty", properties.isCounty),
            },
        ];
    }

    /**
     * Build the popup title for a farmers market feature.
     * The CFM abbreviation is expanded and the market suffix is added only when missing.
     *
     * @param {Record<string, unknown>} properties Feature properties for the farmers market.
     * @returns {string} Display title.
     */
    function buildFarmersMarketTitle(properties) {
        const rawName = getTrimmedString(properties.name);
        if (!rawName) {
            return "Farmers Market";
        }

        const expandedName = rawName.replace(/\bCFM\b/g, "Certified Farmers Market").trim();

        if (/farmers market/i.test(expandedName)) {
            return expandedName;
        }

        return `${expandedName} Farmers Market`;
    }

    /**
     * Build the complete farmers market popup markup.
     * The shared card shell renders the normalized title and ordered market details.
     *
     * @param {Record<string, unknown>} properties Feature properties for the farmers market.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildFarmersMarketPopupContent(properties) {
        return renderPopupCard({
            title: buildFarmersMarketTitle(properties),
            rows: buildFarmersMarketRows(properties),
        });
    }

    registerPopupBuilder("buildFarmersMarketPopupContent", buildFarmersMarketPopupContent);
})();
