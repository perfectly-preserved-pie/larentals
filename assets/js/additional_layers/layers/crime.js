(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (typeof createPopupMarker !== "function" || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the crime layer renderer.");
        return;
    }

    /**
     * Create the crime marker and bind its popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the crime record.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawCrimeIcon(feature, latlng) {
        const crimeIcon = L.icon({
            iconUrl: "/assets/crime_icon.png",
            iconSize: [25, 25],
        });

        return createPopupMarker(
            feature,
            latlng,
            crimeIcon,
            "buildCrimePopupContent"
        );
    }

    registerLayerRenderer("drawCrimeIcon", drawCrimeIcon);
})();
