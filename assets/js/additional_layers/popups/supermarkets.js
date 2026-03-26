(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupUtils = popupApi && popupApi.utils;
    const popupRuntime = popupApi && popupApi.runtime;
    const registerPopupBuilder = popupRuntime && popupRuntime.registerPopupBuilder;

    if (!popupUtils || typeof registerPopupBuilder !== "function") {
        console.error("Additional layer popup utils did not load before the supermarket popup builder.");
        return;
    }

    const escapeHtml = popupUtils.escapeHtml;
    const formatPopupDate = popupUtils.formatPopupDate;
    const getTrimmedString = popupUtils.getTrimmedString;
    const isBlankValue = popupUtils.isBlankValue;
    const joinAddressParts = popupUtils.joinAddressParts;
    const renderPopupCard = popupUtils.renderPopupCard;
    const toDisplayTitleCase = popupUtils.toDisplayTitleCase;

    /**
     * Build the popup title for a supermarket feature.
     *
     * @param {Record<string, unknown>} properties Feature properties for the supermarket.
     * @returns {string} Title for the popup header.
     */
    function buildSupermarketTitle(properties) {
        const dbaName = getTrimmedString(properties.dba_name);
        const businessName = getTrimmedString(properties.business_name);
        return toDisplayTitleCase(dbaName || businessName || "Supermarket / Grocery Store") || "Supermarket / Grocery Store";
    }

    /**
     * Build the formatted address string for a supermarket popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the supermarket.
     * @returns {string} Escaped address string, or `N/A` when unavailable.
     */
    function buildSupermarketAddress(properties) {
        if (!isBlankValue(properties.full_address)) {
            return escapeHtml(toDisplayTitleCase(properties.full_address));
        }

        const address = joinAddressParts([
            properties.street_address,
            properties.city,
            properties.zip_code,
        ]);

        return address ? escapeHtml(toDisplayTitleCase(address)) : "N/A";
    }

    /**
     * Build the category row for a supermarket popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the supermarket.
     * @returns {{ label: string, value: string }|null} Category row, or `null` when no category metadata exists.
     */
    function buildSupermarketCategoryRow(properties) {
        const naics = getTrimmedString(properties.naics);
        if (naics) {
            const description = getTrimmedString(properties.primary_naics_description);
            return {
                label: "NAICS",
                value: description
                    ? `${escapeHtml(naics)} - ${escapeHtml(description)}`
                    : escapeHtml(naics),
            };
        }

        const businessType = getTrimmedString(properties.business_type);
        if (businessType) {
            return {
                label: "Business Type",
                value: escapeHtml(businessType),
            };
        }

        return null;
    }

    /**
     * Build the complete supermarket popup markup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the supermarket.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildSupermarketPopupContent(properties) {
        const rows = [
            {
                label: "Address",
                value: buildSupermarketAddress(properties),
            },
            buildSupermarketCategoryRow(properties),
            isBlankValue(properties.location_start_date) ? null : {
                label: "Opened",
                value: formatPopupDate(properties.location_start_date),
            },
        ];

        return renderPopupCard({
            title: buildSupermarketTitle(properties),
            rows: rows,
        });
    }

    registerPopupBuilder("buildSupermarketPopupContent", buildSupermarketPopupContent);
})();
