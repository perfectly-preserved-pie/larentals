(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (typeof createPopupMarker !== "function" || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the farmers market layer renderer.");
        return;
    }

    /**
     * Create the farmers market marker and bind its popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the farmers market.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawFarmersMarketIcon(feature, latlng) {
        const marketIcon = L.icon({
            iconUrl: "/assets/farmers_market_icon.png",
            iconSize: [25, 25],
        });

        return createPopupMarker(
            feature,
            latlng,
            marketIcon,
            "buildFarmersMarketPopupContent",
            {
                maxWidth: 420,
                minWidth: 320,
            }
        );
    }

    registerLayerRenderer("drawFarmersMarketIcon", drawFarmersMarketIcon);
})();
