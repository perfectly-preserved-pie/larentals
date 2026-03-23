(function() {
    "use strict";

    const popupUtils = window.additionalLayerPopups && window.additionalLayerPopups.utils;

    if (!popupUtils) {
        console.error("Additional layer popup utils did not load before the oil popup builder.");
        return;
    }

    const escapeHtml = popupUtils.escapeHtml;
    const formatPopupDate = popupUtils.formatPopupDate;
    const formatTextValue = popupUtils.formatTextValue;
    const getTrimmedString = popupUtils.getTrimmedString;
    const isBlankValue = popupUtils.isBlankValue;
    const renderPopupCard = popupUtils.renderPopupCard;

    const oilWellStatusLabels = {
        A: "Active",
        B: "Buried",
        I: "Idle",
        N: "New",
        P: "Plugged",
        U: "Unknown",
    };

    const oilWellStatusColors = {
        A: "active",
        B: "buried",
        I: "idle",
        N: "new",
        P: "plugged",
        U: "unknown",
    };

    /**
     * Build the status row value for an oil/gas well popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the well.
     * @returns {string} Styled status value.
     */
    function buildOilWellStatus(properties) {
        const statusCode = getTrimmedString(properties.WellStatus);
        const statusLabel = statusCode && oilWellStatusLabels[statusCode]
            ? `${oilWellStatusLabels[statusCode]} (${statusCode})`
            : (statusCode || "N/A");
        const statusColorClass = statusCode && oilWellStatusColors[statusCode]
            ? oilWellStatusColors[statusCode]
            : "unknown";

        return `<span class="additional-layer-popup__status additional-layer-popup__status--${statusColorClass}">${escapeHtml(statusLabel)}</span>`;
    }

    /**
     * Build the popup title for an oil/gas well feature.
     *
     * @param {Record<string, unknown>} properties Feature properties for the well.
     * @returns {string} Popup title.
     */
    function buildOilWellTitle(properties) {
        const wellNumber = getTrimmedString(properties.WellNumber);
        const fieldName = getTrimmedString(properties.FieldName);
        const apiNumber = getTrimmedString(properties.APINumber) || getTrimmedString(properties.API);

        if (fieldName && wellNumber) {
            return `${fieldName} - Well ${wellNumber}`;
        }

        if (wellNumber) {
            return `Oil/Gas Well Number ${wellNumber}`;
        }

        return `Oil/Gas Well API ${apiNumber || "Unknown"}`;
    }

    /**
     * Build the detail rows rendered in an oil/gas well popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the well.
     * @returns {{ label: string, value: string }[]} Popup rows for the feature.
     */
    function buildOilWellRows(properties) {
        const apiNumber = getTrimmedString(properties.APINumber) || getTrimmedString(properties.API);
        return [
            {
                label: "API Number",
                value: formatTextValue(apiNumber),
            },
            {
                label: "Operator",
                value: formatTextValue(properties.OperatorNa),
            },
            {
                label: "Field Name",
                value: formatTextValue(properties.FieldName),
            },
            {
                label: "County",
                value: formatTextValue(properties.CountyName),
            },
            {
                label: "Start Date",
                value: formatPopupDate(properties.SPUDDate),
            },
            {
                label: "Completion Date",
                value: formatPopupDate(properties.Completion),
            },
            !isBlankValue(properties.AbandonedD) ? {
                label: "Abandoned Date",
                value: formatPopupDate(properties.AbandonedD),
            } : null,
            {
                label: "Latest Update",
                value: formatPopupDate(properties.LatestUpdate),
            },
            {
                label: "Well Status",
                value: buildOilWellStatus(properties),
            },
        ];
    }

    /**
     * Build the complete oil/gas well popup markup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the well.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildOilWellPopupContent(properties) {
        return renderPopupCard({
            title: buildOilWellTitle(properties),
            rows: buildOilWellRows(properties),
        });
    }

    window.additionalLayerPopups = Object.assign({}, window.additionalLayerPopups, {
        builders: Object.assign({}, window.additionalLayerPopups && window.additionalLayerPopups.builders, {
            buildOilWellPopupContent: buildOilWellPopupContent,
        }),
    });
})();
