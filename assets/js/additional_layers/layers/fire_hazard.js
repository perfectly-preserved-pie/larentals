(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const popupUtils = popupApi && popupApi.utils;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (!popupUtils || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the fire hazard layer renderer.");
        return;
    }

    const escapeHtml = popupUtils.escapeHtml;
    const formatTextValue = popupUtils.formatTextValue;
    const renderPopupCard = popupUtils.renderPopupCard;

    const SEVERITY_STYLES = {
        "Moderate": {
            color: "#c79500",
            fillColor: "#ffd84d",
            fillOpacity: 0.18,
        },
        "High": {
            color: "#c96a00",
            fillColor: "#ff9f1c",
            fillOpacity: 0.24,
        },
        "Very High": {
            color: "#b42318",
            fillColor: "#ef4444",
            fillOpacity: 0.3,
        },
    };

    /**
     * Normalize a FHSZ feature severity into a display label.
     *
     * @param {unknown} value Raw severity value.
     * @returns {string} Display label.
     */
    function normalizeSeverity(value) {
        const raw = value === null || value === undefined ? "" : String(value).trim().toLowerCase();
        if (raw.includes("very") && raw.includes("high")) {
            return "Very High";
        }
        if (raw === "high" || raw.endsWith(" high")) {
            return "High";
        }
        if (raw === "moderate" || raw.endsWith(" moderate")) {
            return "Moderate";
        }
        return "Unknown";
    }

    /**
     * Return the Leaflet style for a CAL FIRE FHSZ polygon.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature.
     * @returns {Record<string, unknown>} Leaflet path style.
     */
    function styleFireHazardZone(feature) {
        const properties = feature && feature.properties ? feature.properties : {};
        const severity = normalizeSeverity(properties.fire_hazard_severity);
        const severityStyle = SEVERITY_STYLES[severity] || {
            color: "#6b7280",
            fillColor: "#9ca3af",
            fillOpacity: 0.18,
        };

        return {
            color: severityStyle.color,
            weight: 1,
            opacity: 0.9,
            fillColor: severityStyle.fillColor,
            fillOpacity: severityStyle.fillOpacity,
        };
    }

    function buildSeverityChip(severity) {
        const normalized = normalizeSeverity(severity);
        const classSuffix = normalized.toLowerCase().replace(/\s+/g, "-");
        return `
            <span class="fire-hazard-zone-chip fire-hazard-zone-chip--${escapeHtml(classSuffix)}">
                ${escapeHtml(normalized)}
            </span>
        `;
    }

    function buildDateDisplay(properties) {
        const effectiveDate = properties.fire_hazard_effective_date;
        const rolloutPhase = properties.fire_hazard_rollout_phase;
        if (rolloutPhase) {
            return `${formatTextValue(rolloutPhase)} (${formatTextValue(effectiveDate)})`;
        }
        return formatTextValue(effectiveDate);
    }

    /**
     * Bind popup and hover behavior to a CAL FIRE FHSZ polygon.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature.
     * @param {L.Path} layer Leaflet polygon/path layer.
     * @returns {void}
     */
    function bindFireHazardZonePopup(feature, layer) {
        const properties = feature && feature.properties ? feature.properties : {};
        const severity = normalizeSeverity(properties.fire_hazard_severity);
        const area = properties.fire_hazard_responsibility_area || "FHSZ";

        layer.bindPopup(
            renderPopupCard({
                title: "Fire Hazard Severity Zone",
                rows: [
                    {
                        label: "Severity",
                        value: buildSeverityChip(severity),
                    },
                    {
                        label: "Area",
                        value: formatTextValue(area),
                    },
                    {
                        label: "Effective",
                        value: buildDateDisplay(properties),
                    },
                    {
                        label: "Source",
                        value: formatTextValue(properties.fire_hazard_source || "CAL FIRE"),
                    },
                ],
            }),
            {
                maxWidth: 340,
                className: "responsive-popup",
            }
        );

        layer.on({
            mouseover: function(event) {
                const target = event.target;
                if (target && typeof target.setStyle === "function") {
                    target.setStyle({
                        weight: 2,
                        fillOpacity: Math.min(0.42, (styleFireHazardZone(feature).fillOpacity || 0.2) + 0.1),
                    });
                }
            },
            mouseout: function(event) {
                const target = event.target;
                if (target && typeof target.setStyle === "function") {
                    target.setStyle(styleFireHazardZone(feature));
                }
            },
        });
    }

    registerLayerRenderer("styleFireHazardZone", styleFireHazardZone);
    registerLayerRenderer("bindFireHazardZonePopup", bindFireHazardZonePopup);
})();
