(function() {
    "use strict";

    /**
     * This file intentionally stays thin.
     * Shared popup helpers load from `10_additional_layer_popup_utils.js`
     * and layer-specific popup builders load from `assets/js/additional_layers/*.js`.
     */

    const BREAKFAST_BURRITO_ICON_URL = "https://api.iconify.design/twemoji/burrito.svg?width=18&height=18";

    /**
     * @typedef {{ properties?: Record<string, unknown> }} LayerFeature
     */

    /**
     * Create a marker and bind popup content when properties are present.
     *
     * @param {LayerFeature} feature GeoJSON feature for the marker.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @param {L.Icon|L.DivIcon} icon Marker icon to use.
     * @param {string} builderName Popup content builder name registered on `window.additionalLayerPopups.builders`.
     * @param {Record<string, unknown>=} popupOptions Optional Leaflet popup options.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function createPopupMarker(feature, latlng, icon, builderName, popupOptions) {
        const marker = L.marker(latlng, {icon: icon});

        if (feature.properties) {
            const buildPopupContent = getPopupBuilder(builderName);
            if (buildPopupContent) {
                marker.bindPopup(buildPopupContent(feature.properties), popupOptions);
            }
        }

        return marker;
    }

    /**
     * Resolve a popup builder lazily so folder load order does not break marker registration.
     *
     * @param {string} builderName Popup builder name.
     * @returns {((properties: Record<string, unknown>) => string)|null} Popup builder function or `null`.
     */
    function getPopupBuilder(builderName) {
        const popupBuilders = window.additionalLayerPopups && window.additionalLayerPopups.builders;
        const builder = popupBuilders && popupBuilders[builderName];

        if (typeof builder !== "function") {
            console.error(`Additional layer popup builder "${builderName}" is unavailable.`);
            return null;
        }

        return builder;
    }

    /**
     * Create the oil/gas well marker and bind its popup content.
     *
     * @param {LayerFeature} feature GeoJSON feature for the oil/gas well.
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

    /**
     * Create the crime marker and bind its popup content.
     *
     * @param {LayerFeature} feature GeoJSON feature for the crime record.
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

    /**
     * Create the breakfast burrito marker and bind its popup content.
     *
     * @param {LayerFeature} feature GeoJSON feature for the breakfast burrito location.
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
                        src="${BREAKFAST_BURRITO_ICON_URL}"
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

    /**
     * Create the farmers market marker and bind its popup content.
     *
     * @param {LayerFeature} feature GeoJSON feature for the farmers market.
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

    /**
     * Create the supermarket marker and bind its popup content.
     *
     * @param {LayerFeature} feature GeoJSON feature for the supermarket.
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

    window.myNamespace = Object.assign({}, window.myNamespace, {
        mySubNamespace: Object.assign({}, window.myNamespace && window.myNamespace.mySubNamespace, {
            drawOilIcon: drawOilIcon,
            drawCrimeIcon: drawCrimeIcon,
            drawBreakfastBurritoIcon: drawBreakfastBurritoIcon,
            drawFarmersMarketIcon: drawFarmersMarketIcon,
            drawSupermarketIcon: drawSupermarketIcon,
        }),
    });
})();
