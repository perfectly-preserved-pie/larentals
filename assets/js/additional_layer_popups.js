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
     *   marker_points?: unknown,
     *   heat_max_intensity?: unknown,
     *   max_citation_count?: unknown,
     *   marker_frequency_breaks?: unknown,
     *   marker_zoom_min?: unknown,
     *   heat_zoom_max?: unknown,
     *   window_start?: unknown,
     *   window_end?: unknown,
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
     * @typedef {[number, number, number, number, number, string]} MarkerPointTuple
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
     * weighted hotspots and marker hotspots on that feature. This hook manages a
     * true `L.heatLayer(...)` plus a zoomed-in marker layer so the presentation can
     * transition as users zoom closer to street level.
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
        const rawMarkerPoints = Array.isArray(properties.marker_points)
            ? properties.marker_points
            : [];

        /** @type {HeatPointTuple[]} */
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
        /** @type {MarkerPointTuple[]} */
        const markerPoints = rawMarkerPoints
            .map(function(point) {
                if (!Array.isArray(point) || point.length < 6) {
                    return null;
                }

                const lat = Number(point[0]);
                const lon = Number(point[1]);
                const citationCount = Number(point[2]);
                const totalFineAmount = Number(point[3]);
                const averageFineAmount = Number(point[4]);
                const location = String(point[5] || "").trim();
                if (
                    !Number.isFinite(lat) ||
                    !Number.isFinite(lon) ||
                    !Number.isFinite(citationCount) ||
                    !Number.isFinite(totalFineAmount) ||
                    !Number.isFinite(averageFineAmount) ||
                    !location
                ) {
                    return null;
                }

                return [lat, lon, citationCount, totalFineAmount, averageFineAmount, location];
            })
            .filter(function(point) {
                return Array.isArray(point);
            });
        const popupBuilder = getPopupBuilder("buildParkingTicketsPopupContent");
        const markerZoomMin = Number(properties.marker_zoom_min) || 15;
        const heatZoomMax = Number(properties.heat_zoom_max) || 16;
        const maxCitationCount = Math.max(1, Number(properties.max_citation_count) || 1);
        const markerFrequencyBreaks = Array.isArray(properties.marker_frequency_breaks)
            ? properties.marker_frequency_breaks.map(function(value) {
                return Number(value) || 0;
            })
            : [0, 0, 0, 0];

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
        const markerRenderer = L.canvas({ padding: 0.5 });

        function ensureParkingTicketsMarkerPane(map) {
            if (!map.getPane("parkingTicketsMarkerPane")) {
                const markerPane = map.createPane("parkingTicketsMarkerPane");
                markerPane.style.zIndex = "610";
            }
        }

        function buildMarkerStyle(citationCount) {
            const normalizedCount = Math.sqrt(citationCount / maxCitationCount);
            const q50 = markerFrequencyBreaks[0] || 0;
            const q75 = markerFrequencyBreaks[1] || 0;
            const q90 = markerFrequencyBreaks[2] || 0;
            const q975 = markerFrequencyBreaks[3] || 0;

            let fillColor = "#3da1ff";
            let strokeColor = "#0f1b26";

            if (citationCount >= q975 && q975 > 0) {
                fillColor = "#ff3123";
                strokeColor = "#4f0a06";
            } else if (citationCount >= q90 && q90 > 0) {
                fillColor = "#ff8f1f";
                strokeColor = "#5c2d00";
            } else if (citationCount >= q75 && q75 > 0) {
                fillColor = "#ffd43b";
                strokeColor = "#665200";
            } else if (citationCount >= q50 && q50 > 0) {
                fillColor = "#2ecf7f";
                strokeColor = "#0f4a2a";
            }

            return {
                radius: 4 + (normalizedCount * 6),
                color: strokeColor,
                weight: 2,
                opacity: 0.95,
                fillColor: fillColor,
                fillOpacity: 0.95,
                pane: "parkingTicketsMarkerPane",
                renderer: markerRenderer,
            };
        }

        function createMarkerLayer(map) {
            ensureParkingTicketsMarkerPane(map);

            if (!anchorMarker._parkingTicketsMarkerLayer) {
                anchorMarker._parkingTicketsMarkerLayer = L.layerGroup();
            }

            return anchorMarker._parkingTicketsMarkerLayer;
        }

        function refreshMarkerLayer(map) {
            const markerLayer = createMarkerLayer(map);
            const paddedBounds = map.getBounds().pad(0.2);
            const visiblePoints = markerPoints
                .filter(function(point) {
                    return paddedBounds.contains([point[0], point[1]]);
                })
                .slice(0, 1200);

            markerLayer.clearLayers();

            visiblePoints.forEach(function(point) {
                const markerProperties = {
                    location: point[5],
                    citation_count: point[2],
                    total_fine_amount: point[3],
                    average_fine_amount: point[4],
                    window_start: properties.window_start,
                    window_end: properties.window_end,
                };
                const markerLayerItem = L.circleMarker([point[0], point[1]], buildMarkerStyle(point[2]));

                if (popupBuilder) {
                    markerLayerItem.bindPopup(popupBuilder(markerProperties), {
                        maxWidth: 420,
                        minWidth: 280,
                    });
                }

                markerLayer.addLayer(markerLayerItem);
            });

            if (!map.hasLayer(markerLayer)) {
                markerLayer.addTo(map);
            }
        }

        function hideMarkerLayer(map) {
            if (!anchorMarker._parkingTicketsMarkerLayer) {
                return;
            }

            anchorMarker._parkingTicketsMarkerLayer.clearLayers();
            if (map.hasLayer(anchorMarker._parkingTicketsMarkerLayer)) {
                map.removeLayer(anchorMarker._parkingTicketsMarkerLayer);
            }
        }

        function syncParkingTicketsPresentation() {
            const map = anchorMarker._map;
            if (!map) {
                return;
            }

            const zoom = map.getZoom();
            const showMarkers = zoom >= markerZoomMin;
            const showHeat = zoom < heatZoomMax;

            if (showMarkers && markerPoints.length) {
                refreshMarkerLayer(map);
            } else {
                hideMarkerLayer(map);
            }

            if (!showHeat) {
                if (
                    anchorMarker._parkingTicketsHeatLayer &&
                    map.hasLayer(anchorMarker._parkingTicketsHeatLayer)
                ) {
                    map.removeLayer(anchorMarker._parkingTicketsHeatLayer);
                }
                return;
            }

            if (!heatPoints.length) {
                return;
            }

            ensureLeafletHeatLoaded()
                .then(function() {
                    const liveMap = anchorMarker._map;

                    if (!liveMap) {
                        return;
                    }
                    if (liveMap.getZoom() >= heatZoomMax) {
                        return;
                    }

                    if (!liveMap.getPane("parkingTicketsHeatPane")) {
                        const heatPane = liveMap.createPane("parkingTicketsHeatPane");
                        heatPane.style.zIndex = "390";
                        heatPane.style.pointerEvents = "none";
                    }

                    if (!anchorMarker._parkingTicketsHeatLayer) {
                        anchorMarker._parkingTicketsHeatLayer = L.heatLayer(heatPoints, heatOptions);
                    }

                    if (!liveMap.hasLayer(anchorMarker._parkingTicketsHeatLayer)) {
                        anchorMarker._parkingTicketsHeatLayer.addTo(liveMap);
                    }
                })
                .catch(function(error) {
                    console.error("Parking tickets heatmap could not be mounted.", error);
                });
        }

        anchorMarker.on("add", function() {
            const map = anchorMarker._map;

            if (!map) {
                return;
            }

            anchorMarker._parkingTicketsSync = syncParkingTicketsPresentation;
            map.on("zoomend", anchorMarker._parkingTicketsSync);
            map.on("moveend", anchorMarker._parkingTicketsSync);
            syncParkingTicketsPresentation();
        });

        anchorMarker.on("remove", function() {
            const map = anchorMarker._map;

            if (map && anchorMarker._parkingTicketsSync) {
                map.off("zoomend", anchorMarker._parkingTicketsSync);
                map.off("moveend", anchorMarker._parkingTicketsSync);
            }

            if (anchorMarker._parkingTicketsHeatLayer) {
                if (map && map.hasLayer(anchorMarker._parkingTicketsHeatLayer)) {
                    map.removeLayer(anchorMarker._parkingTicketsHeatLayer);
                }
                anchorMarker._parkingTicketsHeatLayer = null;
            }
            if (map) {
                hideMarkerLayer(map);
            }
            anchorMarker._parkingTicketsMarkerLayer = null;
            anchorMarker._parkingTicketsSync = null;
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
