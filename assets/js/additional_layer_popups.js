(function() {
    "use strict";

    /**
     * This file intentionally stays thin.
     * Shared popup helpers load from `10_additional_layer_popup_utils.js`
     * and layer-specific popup builders load from `assets/js/additional_layers/*.js`.
     */

    const BREAKFAST_BURRITO_ICON_URL = "https://api.iconify.design/twemoji/burrito.svg?width=18&height=18";
    const LEAFLET_HEAT_SCRIPT_URLS = [
        "https://cdn.jsdelivr.net/npm/leaflet.heat@0.2.0/dist/leaflet-heat.js",
        "https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js",
    ];

    /**
     * @typedef {Record<string, unknown>} LayerProperties
     */

    /**
     * @typedef {{ properties?: LayerProperties }} LayerFeature
     */

    /**
     * @typedef {L.PopupOptions} LayerPopupOptions
     */

    /**
     * @typedef {{
     *   layer_role?: unknown,
     *   heat_points?: unknown,
     *   heat_max_intensity?: unknown,
     * } & LayerProperties} ParkingHeatPointProperties
     */

    /**
     * @typedef {{
     *   window_start?: unknown,
     *   window_end?: unknown,
     *   spot_decimals?: unknown,
     *   heat_point_count?: unknown,
     *   max_citation_count?: unknown,
     *   heat_max_intensity?: unknown,
     * }} ParkingHeatMetadata
     */

    /**
     * @typedef {[number, number, number]} HeatPointTuple
     */

    /**
     * Create a marker and bind popup content when properties are present.
     *
     * @param {LayerFeature} feature GeoJSON feature for the marker.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @param {L.Icon|L.DivIcon} icon Marker icon to use.
     * @param {string} builderName Popup content builder name registered on `window.additionalLayerPopups.builders`.
     * @param {LayerPopupOptions=} popupOptions Optional Leaflet popup options.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function createPopupMarker(feature, latlng, icon, builderName, popupOptions) {
        const marker = L.marker(latlng, {icon: icon});

        bindAdditionalLayerPopup(marker, feature, builderName, popupOptions);

        return marker;
    }

    /**
     * Bind popup content to an additional-layer marker/path when possible.
     *
     * @param {L.Layer} layer Leaflet layer to receive the popup.
     * @param {LayerFeature} feature GeoJSON feature for the layer.
     * @param {string} builderName Popup content builder name.
     * @param {LayerPopupOptions=} popupOptions Optional Leaflet popup options.
     * @returns {void}
     */
    function bindAdditionalLayerPopup(layer, feature, builderName, popupOptions) {
        if (!feature.properties) {
            return;
        }

        const buildPopupContent = getPopupBuilder(builderName);
        if (buildPopupContent) {
            layer.bindPopup(buildPopupContent(feature.properties), popupOptions);
        }
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
     * Ensure the Leaflet heatmap plugin is available before mounting the layer.
     *
     * This avoids depending on global script load order, which is brittle with
     * Dash component bundles and external CDN scripts.
     *
     * @returns {Promise<void>} Promise that resolves once `L.heatLayer` is ready.
     */
    function ensureLeafletHeatLoaded() {
        if (typeof L !== "undefined" && typeof L.heatLayer === "function") {
            return Promise.resolve();
        }

        if (window.larentalsLeafletHeatPromise) {
            return window.larentalsLeafletHeatPromise;
        }

        window.larentalsLeafletHeatPromise = new Promise(function(resolve, reject) {
            if (typeof document === "undefined") {
                reject(new Error("Document is unavailable; cannot load Leaflet heatmap plugin."));
                return;
            }

            let scriptIndex = 0;

            function tryNextScript() {
                if (typeof L !== "undefined" && typeof L.heatLayer === "function") {
                    resolve();
                    return;
                }

                if (scriptIndex >= LEAFLET_HEAT_SCRIPT_URLS.length) {
                    reject(new Error("Unable to load Leaflet heatmap plugin from the configured CDNs."));
                    return;
                }

                const scriptUrl = LEAFLET_HEAT_SCRIPT_URLS[scriptIndex++];
                const existingScript = Array.from(document.scripts || []).find(function(scriptTag) {
                    return scriptTag.src === scriptUrl;
                });

                if (existingScript) {
                    existingScript.addEventListener("load", tryNextScript, { once: true });
                    existingScript.addEventListener("error", tryNextScript, { once: true });
                    return;
                }

                const scriptTag = document.createElement("script");
                scriptTag.src = scriptUrl;
                scriptTag.async = true;
                scriptTag.onload = tryNextScript;
                scriptTag.onerror = tryNextScript;
                document.head.appendChild(scriptTag);
            }

            tryNextScript();
        }).catch(function(error) {
            console.error("Leaflet heatmap plugin failed to load.", error);
            window.larentalsLeafletHeatPromise = null;
            throw error;
        });

        return window.larentalsLeafletHeatPromise;
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

    /**
     * Create the invisible anchor marker used to mount a true Leaflet heat layer.
     *
     * Dash Leaflet renders one Leaflet layer per GeoJSON feature. For the parking
     * heatmap we only return a single invisible point feature and store the real
     * weighted hotspots on that feature as `properties.heat_points`. This hook reads
     * those points, creates `L.heatLayer(...)`, and keeps it attached while the
     * overlay stays enabled.
     *
     * @param {LayerFeature} feature GeoJSON anchor feature for the parking heatmap.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Invisible marker that owns the heat layer lifecycle.
     */
    function drawParkingHeatLayer(feature, latlng) {
        /** @type {ParkingHeatPointProperties} */
        const properties = feature && feature.properties ? feature.properties : {};
        const rawHeatPoints = Array.isArray(properties.heat_points)
            ? properties.heat_points
            : [];

        const heatPoints = rawHeatPoints
            .map(function(point) {
                if (!Array.isArray(point) || point.length < 3) {
                    return null;
                }

                const lat = Number(point[0]);
                const lon = Number(point[1]);
                const intensity = Number(point[2]);
                if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(intensity)) {
                    return null;
                }

                return [lat, lon, intensity];
            })
            .filter(function(point) {
                return Array.isArray(point);
            });

        const anchorMarker = L.marker(latlng, {
            opacity: 0,
            interactive: false,
            keyboard: false,
            bubblingMouseEvents: false,
        });

        const heatOptions = {
            pane: "parkingTicketsHeatPane",
            radius: 20,
            blur: 18,
            maxZoom: 16,
            minOpacity: 0.24,
            max: Number(properties.heat_max_intensity) || 1,
            gradient: {
                0.18: "#2748ff",
                0.36: "#00b6ff",
                0.54: "#19d889",
                0.72: "#ffe34d",
                0.88: "#ff9730",
                1.0: "#ff2f1f",
            },
        };

        anchorMarker.on("add", function() {
            if (!heatPoints.length) {
                return;
            }

            ensureLeafletHeatLoaded()
                .then(function() {
                    const map = anchorMarker._map;

                    if (!map) {
                        return;
                    }

                    if (!map.getPane("parkingTicketsHeatPane")) {
                        const heatPane = map.createPane("parkingTicketsHeatPane");
                        heatPane.style.zIndex = "390";
                        heatPane.style.pointerEvents = "none";
                    }

                    if (
                        anchorMarker._parkingTicketsHeatLayer &&
                        map.hasLayer(anchorMarker._parkingTicketsHeatLayer)
                    ) {
                        return;
                    }

                    anchorMarker._parkingTicketsHeatLayer = L.heatLayer(heatPoints, heatOptions);
                    anchorMarker._parkingTicketsHeatLayer.addTo(map);
                })
                .catch(function(error) {
                    console.error("Parking tickets heatmap could not be mounted.", error);
                });
        });

        anchorMarker.on("remove", function() {
            const map = anchorMarker._map;

            if (!anchorMarker._parkingTicketsHeatLayer) {
                return;
            }

            if (map && map.hasLayer(anchorMarker._parkingTicketsHeatLayer)) {
                map.removeLayer(anchorMarker._parkingTicketsHeatLayer);
            }
            anchorMarker._parkingTicketsHeatLayer = null;
        });

        return anchorMarker;
    }

    window.myNamespace = Object.assign({}, window.myNamespace, {
        mySubNamespace: Object.assign({}, window.myNamespace && window.myNamespace.mySubNamespace, {
            drawOilIcon: drawOilIcon,
            drawCrimeIcon: drawCrimeIcon,
            drawBreakfastBurritoIcon: drawBreakfastBurritoIcon,
            drawFarmersMarketIcon: drawFarmersMarketIcon,
            drawSupermarketIcon: drawSupermarketIcon,
            drawParkingHeatLayer: drawParkingHeatLayer,
        }),
    });
})();
