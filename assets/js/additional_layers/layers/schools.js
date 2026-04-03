(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (typeof createPopupMarker !== "function" || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the schools layer renderer.");
        return;
    }

    /**
     * Resolve a marker color chip class from the school level.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} CSS class for the marker chip.
     */
    function resolveSchoolMarkerClass(properties) {
        const level = String(properties && properties.school_level || "").toLowerCase();

        if (level.includes("elementary")) {
            return "school-marker__chip school-marker__chip--elementary";
        }
        if (level.includes("middle")) {
            return "school-marker__chip school-marker__chip--middle";
        }
        if (level.includes("high") || level.includes("secondary")) {
            return "school-marker__chip school-marker__chip--high";
        }
        return "school-marker__chip school-marker__chip--other";
    }

    /**
     * Create the school marker and bind popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the school.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawSchoolIcon(feature, latlng) {
        const schoolIcon = L.divIcon({
            className: "school-div-icon",
            html: `
                <div class="${resolveSchoolMarkerClass(feature && feature.properties || {})}">
                    <span class="school-marker__symbol">🏫</span>
                </div>
            `,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
            popupAnchor: [0, -12],
        });

        return createPopupMarker(
            feature,
            latlng,
            schoolIcon,
            "buildSchoolPopupContent",
            {
                maxWidth: 460,
                minWidth: 340,
            }
        );
    }

    registerLayerRenderer("drawSchoolIcon", drawSchoolIcon);
})();
