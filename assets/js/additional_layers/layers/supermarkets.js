(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (typeof createPopupMarker !== "function" || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the supermarket layer renderer.");
        return;
    }

    /**
     * Create the supermarket marker and bind its popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the supermarket.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawSupermarketIcon(feature, latlng) {
        const supermarketIcon = L.divIcon({
            className: "supermarket-div-icon",
            html: `
                <div class="supermarket-marker__chip">
                    <span class="supermarket-marker__symbol">&#128722;</span>
                </div>
            `,
            iconSize: [22, 22],
            iconAnchor: [11, 11],
            popupAnchor: [0, -12],
        });

        return createPopupMarker(
            feature,
            latlng,
            supermarketIcon,
            "buildSupermarketPopupContent",
            {
                maxWidth: 420,
                minWidth: 320,
            }
        );
    }

    registerLayerRenderer("drawSupermarketIcon", drawSupermarketIcon);
})();
