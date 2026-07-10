(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupUtils = popupApi && popupApi.utils;
    const popupRuntime = popupApi && popupApi.runtime;
    const registerPopupBuilder = popupRuntime && popupRuntime.registerPopupBuilder;

    if (!popupUtils || typeof registerPopupBuilder !== "function") {
        console.error("Additional layer popup utils did not load before the ALPR camera popup builder.");
        return;
    }

    const buildExternalLink = popupUtils.buildExternalLink;
    const escapeHtml = popupUtils.escapeHtml;
    const formatPopupDate = popupUtils.formatPopupDate;
    const formatTextValue = popupUtils.formatTextValue;
    const getTrimmedString = popupUtils.getTrimmedString;
    const isBlankValue = popupUtils.isBlankValue;
    const renderPopupCard = popupUtils.renderPopupCard;

    /**
     * Build the popup title for an ALPR feature.
     *
     * @param {Record<string, unknown>} properties Feature properties.
     * @returns {string} Popup title.
     */
    function buildAlprCameraTitle(properties) {
        const brand = getTrimmedString(properties.brand);
        const operator = getTrimmedString(properties.operator);
        if (brand && operator && brand.toLowerCase() !== operator.toLowerCase()) {
            return `${brand} ALPR`;
        }
        if (brand) {
            return `${brand} ALPR`;
        }
        if (operator) {
            return `${operator} ALPR`;
        }
        return "ALPR Camera";
    }

    /**
     * Format one or more camera bearings.
     *
     * @param {Record<string, unknown>} properties Feature properties.
     * @returns {string} Direction label or `N/A`.
     */
    function buildDirectionValue(properties) {
        const directionCardinal = getTrimmedString(properties.directionCardinal);
        if (directionCardinal) {
            return escapeHtml(directionCardinal);
        }

        if (Array.isArray(properties.directions) && properties.directions.length) {
            return properties.directions
                .map(function(value) {
                    const numberValue = Number(value);
                    return Number.isFinite(numberValue) ? `${Math.round(numberValue)}°` : null;
                })
                .filter(Boolean)
                .join(", ") || "N/A";
        }

        const direction = Number(properties.direction);
        if (Number.isFinite(direction)) {
            return `${Math.round(direction)}°`;
        }
        return "N/A";
    }

    /**
     * Build compact attribution text for the popup body.
     *
     * @param {Record<string, unknown>} properties Feature properties.
     * @returns {string} Attribution banner HTML.
     */
    function buildAlprAttributionBanner(properties) {
        const osmLink = buildExternalLink(properties.osmUrl, "OpenStreetMap record");
        return `
            <div class="additional-layer-popup__attribution">
                <div class="additional-layer-popup__attribution-title">Source Attribution</div>
                <div>
                    ALPR camera feed by
                    ${buildExternalLink("https://maps.deflock.org/", "DeFlock Maps")}
                    /
                    ${buildExternalLink("https://dontgetflocked.com/", "FlockHopper")},
                    derived from ${osmLink}.
                </div>
            </div>
        `;
    }

    /**
     * Build the complete popup markup.
     *
     * @param {Record<string, unknown>} properties Feature properties.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildAlprCameraPopupContent(properties) {
        const rows = [
            {
                label: "Operator",
                value: formatTextValue(properties.operator),
            },
            {
                label: "Brand",
                value: formatTextValue(properties.brand),
            },
            {
                label: "Direction",
                value: buildDirectionValue(properties),
            },
            isBlankValue(properties.surveillanceZone) ? null : {
                label: "Zone",
                value: formatTextValue(properties.surveillanceZone),
            },
            isBlankValue(properties.mountType) ? null : {
                label: "Mount",
                value: formatTextValue(properties.mountType),
            },
            isBlankValue(properties.ref) ? null : {
                label: "Reference",
                value: formatTextValue(properties.ref),
            },
            isBlankValue(properties.startDate) ? null : {
                label: "Start Date",
                value: formatPopupDate(properties.startDate),
            },
            isBlankValue(properties.osmTimestamp) ? null : {
                label: "OSM Updated",
                value: formatPopupDate(properties.osmTimestamp),
            },
        ];

        return renderPopupCard({
            title: buildAlprCameraTitle(properties),
            banner: buildAlprAttributionBanner(properties),
            rows: rows,
        });
    }

    registerPopupBuilder("buildAlprCameraPopupContent", buildAlprCameraPopupContent);
})();
