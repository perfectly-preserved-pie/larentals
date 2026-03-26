(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (typeof createPopupMarker !== "function" || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the oil and gas layer renderer.");
        return;
    }

    /**
     * Create the oil/gas well marker and bind its popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the oil/gas well.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawOilIcon(feature, latlng) {
        const oilIcon = L.icon({
            iconUrl: "/assets/oil_derrick_icon.png",
            iconSize: [20, 20],
        });

        return createPopupMarker(
            feature,
            latlng,
            oilIcon,
            "buildOilWellPopupContent"
        );
    }

    registerLayerRenderer("drawOilIcon", drawOilIcon);
})();
