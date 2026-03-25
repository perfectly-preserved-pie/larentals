(function() {
    "use strict";

    const popupUtils = window.additionalLayerPopups && window.additionalLayerPopups.utils;

    if (!popupUtils) {
        console.error("Additional layer popup utils did not load before the parking tickets popup builder.");
        return;
    }

    const escapeHtml = popupUtils.escapeHtml;
    const formatPopupDate = popupUtils.formatPopupDate;
    const renderPopupCard = popupUtils.renderPopupCard;

    /**
     * @typedef {{
     *   citation_count?: unknown,
     *   total_fine_amount?: unknown,
     *   average_fine_amount?: unknown,
     *   window_start?: unknown,
     *   window_end?: unknown,
     * }} ParkingDensityProperties
     */

    /**
     * @typedef {{ label: string, value: string }} PopupRow
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
     * Format a numeric value as USD for popup display.
     *
     * @param {unknown} value Raw numeric value.
     * @returns {string} Currency string or `N/A`.
     */
    function formatCurrency(value) {
        const numberValue = Number(value);
        if (!Number.isFinite(numberValue)) {
            return "N/A";
        }

        return escapeHtml(
            numberValue.toLocaleString("en-US", {
                style: "currency",
                currency: "USD",
                maximumFractionDigits: 0,
            })
        );
    }

    /**
     * Build the ordered rows rendered in a parking-hotspot popup.
     *
     * @param {ParkingDensityProperties} properties Feature properties for the hotspot.
     * @returns {PopupRow[]} Popup rows for the feature.
     */
    function buildParkingTicketRows(properties) {
        return [
            {
                label: "Tickets at Spot",
                value: formatWholeNumber(properties.citation_count),
            },
            {
                label: "Total Fines",
                value: formatCurrency(properties.total_fine_amount),
            },
            {
                label: "Average Fine",
                value: formatCurrency(properties.average_fine_amount),
            },
            {
                label: "Window Start",
                value: formatPopupDate(properties.window_start),
            },
            {
                label: "Window End",
                value: formatPopupDate(properties.window_end),
            },
        ];
    }

    /**
     * Build the popup title for a parking hotspot.
     *
     * @param {ParkingDensityProperties} properties Feature properties for the hotspot.
     * @returns {string} Popup title.
     */
    function buildParkingTicketsTitle(properties) {
        const citationCount = Number(properties.citation_count);
        if (!Number.isFinite(citationCount) || citationCount <= 0) {
            return "Parking Ticket Density";
        }

        return `${Math.round(citationCount).toLocaleString("en-US")} Parking Tickets`;
    }

    /**
     * Build the complete parking-hotspot popup markup.
     *
     * @param {ParkingDensityProperties} properties Feature properties for the hotspot.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildParkingTicketsPopupContent(properties) {
        return renderPopupCard({
            title: buildParkingTicketsTitle(properties),
            rows: buildParkingTicketRows(properties),
        });
    }

    window.additionalLayerPopups = Object.assign({}, window.additionalLayerPopups, {
        builders: Object.assign({}, window.additionalLayerPopups && window.additionalLayerPopups.builders, {
            buildParkingTicketsPopupContent: buildParkingTicketsPopupContent,
        }),
    });
})();
