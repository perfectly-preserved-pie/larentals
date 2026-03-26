(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupConstants = popupApi && popupApi.constants;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;
    const breakfastBurritoIconUrl = popupConstants && popupConstants.BREAKFAST_BURRITO_ICON_URL;

    if (
        typeof createPopupMarker !== "function" ||
        typeof registerLayerRenderer !== "function" ||
        !breakfastBurritoIconUrl
    ) {
        console.error("Additional layer popup runtime did not load before the breakfast burrito layer renderer.");
        return;
    }

    /**
     * Create the breakfast burrito marker and bind its popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the breakfast burrito location.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawBreakfastBurritoIcon(feature, latlng) {
        const breakfastBurritoIcon = L.divIcon({
            className: "breakfast-burrito-div-icon",
            html: `
                <div class="breakfast-burrito-marker__chip">
                    <img
                        class="breakfast-burrito-marker__icon"
                        src="${breakfastBurritoIconUrl}"
                        alt=""
                        width="18"
                        height="18"
                    >
                </div>
            `,
            iconSize: [28, 22],
            iconAnchor: [14, 11],
            popupAnchor: [0, -12],
        });

        return createPopupMarker(
            feature,
            latlng,
            breakfastBurritoIcon,
            "buildBreakfastBurritoPopupContent",
            {
                maxWidth: 440,
                minWidth: 320,
            }
        );
    }

    registerLayerRenderer("drawBreakfastBurritoIcon", drawBreakfastBurritoIcon);
})();
