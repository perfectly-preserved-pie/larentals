(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const ensureLeafletHeatLoaded = popupRuntime && popupRuntime.ensureLeafletHeatLoaded;
    const getPopupBuilder = popupRuntime && popupRuntime.getPopupBuilder;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (
        typeof ensureLeafletHeatLoaded !== "function" ||
        typeof getPopupBuilder !== "function" ||
        typeof registerLayerRenderer !== "function"
    ) {
        console.error("Additional layer popup runtime did not load before the LAHD layer renderer.");
        return;
    }

    /**
     * @typedef {[number, number, number]} LahdHeatPointTuple
     */

    /**
     * @typedef {[number, number, number, number, number, number, number, number, number, number, number, number, string, string, string | null, string | null]} LahdMarkerPointTuple
     */

    /**
     * @typedef {{ showHeat: boolean, showMarkers: boolean }} LahdLegendOptions
     */

    /**
     * Format problem counts for compact legend labels.
     *
     * @param {unknown} value Candidate count.
     * @returns {string} Localized count label.
     */
    function formatCount(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }

        return Math.round(numericValue).toLocaleString("en-US");
    }

    /**
     * Return a sanitized ascending threshold list.
     *
     * @param {unknown} rawBreaks Raw threshold payload.
     * @returns {number[]} Four ascending marker thresholds.
     */
    function normalizeMarkerBreaks(rawBreaks) {
        const breaks = Array.isArray(rawBreaks)
            ? rawBreaks
                .map(function(value) {
                    return Math.round(Number(value) || 0);
                })
                .filter(function(value) {
                    return Number.isFinite(value) && value > 0;
                })
            : [];

        while (breaks.length < 4) {
            breaks.push(0);
        }

        return breaks.slice(0, 4);
    }

    /**
     * Create the invisible anchor marker used to mount the LAHD heat layer.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON anchor feature.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by Dash Leaflet.
     * @returns {L.Marker} Invisible marker that owns the heat layer lifecycle.
     */
    function drawLahdPropertyHeatLayer(feature, latlng) {
        const properties = feature && feature.properties ? feature.properties : {};
        const rawHeatPoints = Array.isArray(properties.heat_points)
            ? properties.heat_points
            : [];
        const rawMarkerPoints = Array.isArray(properties.marker_points)
            ? properties.marker_points
            : [];

        /** @type {LahdHeatPointTuple[]} */
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

        /** @type {LahdMarkerPointTuple[]} */
        const markerPoints = rawMarkerPoints
            .map(function(point) {
                if (!Array.isArray(point) || point.length < 14) {
                    return null;
                }

                const parsed = [
                    Number(point[0]),
                    Number(point[1]),
                    Number(point[2]),
                    Number(point[3]),
                    Number(point[4]),
                    Number(point[5]),
                    Number(point[6]),
                    Number(point[7]),
                    Number(point[8]),
                    Number(point[9]),
                    Number(point[10]),
                    Number(point[11]),
                ];
                const address = String(point[12] || "").trim();
                const apn = String(point[13] || "").trim();
                const firstCaseDate = point[14] == null ? null : String(point[14]);
                const latestCaseDate = point[15] == null ? null : String(point[15]);

                if (
                    parsed.some(function(value) {
                        return !Number.isFinite(value);
                    }) ||
                    !address
                ) {
                    return null;
                }

                return [
                    parsed[0],
                    parsed[1],
                    parsed[2],
                    parsed[3],
                    parsed[4],
                    parsed[5],
                    parsed[6],
                    parsed[7],
                    parsed[8],
                    parsed[9],
                    parsed[10],
                    parsed[11],
                    address,
                    apn,
                    firstCaseDate,
                    latestCaseDate,
                ];
            })
            .filter(function(point) {
                return Array.isArray(point);
            });

        const popupBuilder = getPopupBuilder("buildLahdPropertyPopupContent");
        const markerZoomMin = Number(properties.marker_zoom_min) || 15;
        const heatZoomMax = Number(properties.heat_zoom_max) || 16;
        const maxProblemScore = Math.max(1, Number(properties.max_problem_score) || 1);
        const markerScoreBreaks = normalizeMarkerBreaks(properties.marker_score_breaks);
        const markerRenderer = L.canvas({ padding: 0.5 });

        const anchorMarker = L.marker(latlng, {
            opacity: 0,
            interactive: false,
            keyboard: false,
            bubblingMouseEvents: false,
        });

        const heatOptions = {
            pane: "lahdPropertyHeatPane",
            radius: 22,
            blur: 20,
            maxZoom: 16,
            minOpacity: 0.22,
            max: Number(properties.heat_max_intensity) || 1,
            gradient: {
                0.18: "#1d4ed8",
                0.36: "#0891b2",
                0.54: "#22c55e",
                0.72: "#facc15",
                0.88: "#f97316",
                1.0: "#dc2626",
            },
        };

        /**
         * Lazily create the Leaflet legend control owned by this overlay instance.
         *
         * @returns {L.Control} Legend control for the LAHD layer.
         */
        function ensureLegendControl() {
            if (anchorMarker._lahdPropertyLegendControl) {
                return anchorMarker._lahdPropertyLegendControl;
            }

            anchorMarker._lahdPropertyLegendControl = L.control({ position: "topright" });
            anchorMarker._lahdPropertyLegendControl.onAdd = function() {
                const container = L.DomUtil.create(
                    "div",
                    "leaflet-control lahd-property-legend"
                );
                container.style.minWidth = "220px";
                container.style.maxWidth = "250px";
                container.style.padding = "12px 14px";
                container.style.border = "1px solid rgba(15, 27, 38, 0.18)";
                container.style.borderRadius = "14px";
                container.style.background = "rgba(255, 255, 255, 0.94)";
                container.style.boxShadow = "0 10px 24px rgba(15, 27, 38, 0.18)";
                container.style.color = "#0f1b26";
                container.style.backdropFilter = "blur(8px)";
                container.style.marginTop = "10px";
                container.style.marginRight = "10px";
                container.style.fontFamily = "system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif";
                L.DomEvent.disableClickPropagation(container);
                L.DomEvent.disableScrollPropagation(container);
                anchorMarker._lahdPropertyLegendContainer = container;
                return container;
            };

            return anchorMarker._lahdPropertyLegendControl;
        }

        /**
         * Rebuild legend contents to match the current zoom presentation.
         *
         * @param {LahdLegendOptions | null | undefined} options Current legend visibility state.
         * @returns {void}
         */
        function renderLegend(options) {
            if (!anchorMarker._lahdPropertyLegendContainer) {
                return;
            }

            const showHeat = Boolean(options && options.showHeat);
            const showMarkers = Boolean(options && options.showMarkers);
            const tier2 = markerScoreBreaks[0] || 0;
            const tier3 = markerScoreBreaks[1] || 0;
            const tier4 = markerScoreBreaks[2] || 0;
            const tier5 = markerScoreBreaks[3] || 0;
            const windowLabel = [
                String(properties.window_start || "").trim(),
                String(properties.window_end || "").trim(),
            ]
                .filter(Boolean)
                .join(" to ");
            const sections = [];

            if (showHeat) {
                sections.push(
                    [
                        '<div style="margin-top: 10px;">',
                        '<div style="margin-bottom: 6px; font-size: 0.78rem; font-weight: 600;">Problem density</div>',
                        '<div aria-hidden="true" style="height: 10px; border-radius: 999px; background: linear-gradient(90deg, #1d4ed8 0%, #0891b2 22%, #22c55e 46%, #facc15 68%, #f97316 84%, #dc2626 100%);"></div>',
                        '<div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 0.72rem; color: #556270;">',
                        "<span>Lower</span>",
                        "<span>Higher</span>",
                        "</div>",
                        "</div>",
                    ].join("")
                );
            }

            if (showMarkers) {
                const markerLegendEntries = [
                    ["#38bdf8", "Lower", tier2 > 0 ? "< " + formatCount(tier2) : null],
                    ["#22c55e", "Elevated", tier2 > 0 && tier3 > 0 ? formatCount(tier2) + "\u2013" + formatCount(tier3 - 1) : null],
                    ["#facc15", "High", tier3 > 0 && tier4 > 0 ? formatCount(tier3) + "\u2013" + formatCount(tier4 - 1) : null],
                    ["#f97316", "Severe", tier4 > 0 && tier5 > 0 ? formatCount(tier4) + "\u2013" + formatCount(tier5 - 1) : null],
                    ["#dc2626", "Extreme", tier5 > 0 ? formatCount(tier5) + "+" : null],
                ];

                sections.push(
                    [
                        '<div style="margin-top: 10px;">',
                        '<div style="margin-bottom: 6px; font-size: 0.78rem; font-weight: 600;">Property score</div>',
                        '<div style="display: grid; gap: 5px;">',
                        markerLegendEntries
                            .filter(function(item) {
                                return item[2];
                            })
                            .map(function(item) {
                                return [
                                    '<div style="display: flex; align-items: center; gap: 8px; font-size: 0.74rem; line-height: 1.25;">',
                                    '<span style="display: inline-block; width: 10px; height: 10px; flex: 0 0 10px; border: 1px solid rgba(15, 27, 38, 0.35); border-radius: 999px; background:',
                                    item[0],
                                    ';"></span>',
                                    '<span style="color: #1f2d3a;">',
                                    item[1],
                                    " (",
                                    item[2],
                                    ")</span>",
                                    "</div>",
                                ].join("");
                            })
                            .join(""),
                        "</div>",
                        "</div>",
                    ].join("")
                );
            }

            anchorMarker._lahdPropertyLegendContainer.innerHTML = [
                '<div style="font-size: 0.95rem; font-weight: 700; line-height: 1.2;">Housing cases & code violations</div>',
                windowLabel
                    ? '<div style="margin-top: 2px; font-size: 0.72rem; color: #556270;">' + windowLabel + "</div>"
                    : "",
                sections.join(""),
                '<div style="margin-top: 10px; font-size: 0.7rem; color: #556270;">Score combines documented and unresolved housing cases/citations.</div>',
            ].join("");
        }

        /**
         * Ensure the legend control is mounted and refreshed.
         *
         * @param {L.Map} map Active Leaflet map.
         * @param {LahdLegendOptions} options Current legend visibility state.
         * @returns {void}
         */
        function syncLegend(map, options) {
            const legendControl = ensureLegendControl();
            if (!map._controlCorners || !map._controlContainer) {
                return;
            }

            if (!map._lahdPropertyLegendMounted) {
                legendControl.addTo(map);
                map._lahdPropertyLegendMounted = true;
            }

            renderLegend(options);
        }

        /**
         * Remove the LAHD legend when the overlay is unmounted.
         *
         * @param {L.Map | null | undefined} map Active Leaflet map.
         * @returns {void}
         */
        function removeLegend(map) {
            if (
                map &&
                anchorMarker._lahdPropertyLegendControl &&
                map._lahdPropertyLegendMounted
            ) {
                anchorMarker._lahdPropertyLegendControl.remove();
                map._lahdPropertyLegendMounted = false;
            }

            anchorMarker._lahdPropertyLegendContainer = null;
        }

        /**
         * Ensure the marker pane exists above listing markers.
         *
         * @param {L.Map} map Active Leaflet map.
         * @returns {void}
         */
        function ensureMarkerPane(map) {
            if (!map.getPane("lahdPropertyMarkerPane")) {
                const markerPane = map.createPane("lahdPropertyMarkerPane");
                markerPane.style.zIndex = "612";
            }
        }

        /**
         * Build circle marker style by score tier.
         *
         * @param {number} problemScore Combined LAHD score.
         * @returns {L.CircleMarkerOptions} Marker style.
         */
        function buildMarkerStyle(problemScore) {
            const normalizedScore = Math.sqrt(problemScore / maxProblemScore);
            const tier2 = markerScoreBreaks[0] || 0;
            const tier3 = markerScoreBreaks[1] || 0;
            const tier4 = markerScoreBreaks[2] || 0;
            const tier5 = markerScoreBreaks[3] || 0;

            let fillColor = "#38bdf8";
            let strokeColor = "#0f1b26";

            if (problemScore >= tier5 && tier5 > 0) {
                fillColor = "#dc2626";
                strokeColor = "#4f0a06";
            } else if (problemScore >= tier4 && tier4 > 0) {
                fillColor = "#f97316";
                strokeColor = "#5c2d00";
            } else if (problemScore >= tier3 && tier3 > 0) {
                fillColor = "#facc15";
                strokeColor = "#665200";
            } else if (problemScore >= tier2 && tier2 > 0) {
                fillColor = "#22c55e";
                strokeColor = "#0f4a2a";
            }

            return {
                radius: 4 + (normalizedScore * 7),
                color: strokeColor,
                weight: 2,
                opacity: 0.95,
                fillColor: fillColor,
                fillOpacity: 0.95,
                pane: "lahdPropertyMarkerPane",
                renderer: markerRenderer,
            };
        }

        /**
         * Create or return the marker layer group.
         *
         * @param {L.Map} map Active Leaflet map.
         * @returns {L.LayerGroup} Marker layer group.
         */
        function createMarkerLayer(map) {
            ensureMarkerPane(map);

            if (!anchorMarker._lahdPropertyMarkerLayer) {
                anchorMarker._lahdPropertyMarkerLayer = L.layerGroup();
            }

            return anchorMarker._lahdPropertyMarkerLayer;
        }

        /**
         * Refresh visible zoomed-in property markers.
         *
         * @param {L.Map} map Active Leaflet map.
         * @returns {void}
         */
        function refreshMarkerLayer(map) {
            const markerLayer = createMarkerLayer(map);
            const paddedBounds = map.getBounds().pad(0.2);
            const visiblePoints = markerPoints
                .filter(function(point) {
                    return paddedBounds.contains([point[0], point[1]]);
                })
                .slice(0, 1400);

            markerLayer.clearLayers();

            visiblePoints.forEach(function(point) {
                const markerProperties = {
                    problem_score: point[2],
                    documented_issue_count: point[3],
                    unresolved_issue_count: point[4],
                    investigation_case_count: point[5],
                    open_case_count: point[6],
                    violations_cited: point[7],
                    unresolved_violation_count: point[8],
                    violation_row_count: point[9],
                    closed_case_count: point[10],
                    violations_cleared: point[11],
                    address: point[12],
                    apn: point[13],
                    first_case_date: point[14],
                    latest_case_date: point[15],
                };
                const markerLayerItem = L.circleMarker([point[0], point[1]], buildMarkerStyle(point[2]));

                if (popupBuilder) {
                    markerLayerItem.bindPopup(popupBuilder(markerProperties), {
                        maxWidth: 430,
                        minWidth: 290,
                    });
                }

                markerLayer.addLayer(markerLayerItem);
            });

            if (!map.hasLayer(markerLayer)) {
                markerLayer.addTo(map);
            }
        }

        /**
         * Hide and clear the marker layer.
         *
         * @param {L.Map} map Active Leaflet map.
         * @returns {void}
         */
        function hideMarkerLayer(map) {
            if (!anchorMarker._lahdPropertyMarkerLayer) {
                return;
            }

            anchorMarker._lahdPropertyMarkerLayer.clearLayers();
            if (map.hasLayer(anchorMarker._lahdPropertyMarkerLayer)) {
                map.removeLayer(anchorMarker._lahdPropertyMarkerLayer);
            }
        }

        /**
         * Sync heat and marker presentation to the current zoom.
         *
         * @returns {void}
         */
        function syncLahdPropertyPresentation() {
            const map = anchorMarker._map;
            if (!map) {
                return;
            }

            const zoom = map.getZoom();
            const showMarkers = zoom >= markerZoomMin;
            const showHeat = zoom < heatZoomMax;
            syncLegend(map, { showHeat: showHeat, showMarkers: showMarkers });

            if (showMarkers && markerPoints.length) {
                refreshMarkerLayer(map);
            } else {
                hideMarkerLayer(map);
            }

            if (!showHeat) {
                if (
                    anchorMarker._lahdPropertyHeatLayer &&
                    map.hasLayer(anchorMarker._lahdPropertyHeatLayer)
                ) {
                    map.removeLayer(anchorMarker._lahdPropertyHeatLayer);
                }
                return;
            }

            if (!heatPoints.length) {
                return;
            }

            ensureLeafletHeatLoaded()
                .then(function() {
                    const liveMap = anchorMarker._map;

                    if (!liveMap || liveMap.getZoom() >= heatZoomMax) {
                        return;
                    }

                    if (!liveMap.getPane("lahdPropertyHeatPane")) {
                        const heatPane = liveMap.createPane("lahdPropertyHeatPane");
                        heatPane.style.zIndex = "392";
                        heatPane.style.pointerEvents = "none";
                    }

                    if (!anchorMarker._lahdPropertyHeatLayer) {
                        anchorMarker._lahdPropertyHeatLayer = L.heatLayer(heatPoints, heatOptions);
                    }

                    if (!liveMap.hasLayer(anchorMarker._lahdPropertyHeatLayer)) {
                        anchorMarker._lahdPropertyHeatLayer.addTo(liveMap);
                    }
                })
                .catch(function(error) {
                    console.error("LAHD property heatmap could not be mounted.", error);
                });
        }

        anchorMarker.on("add", function() {
            const map = anchorMarker._map;

            if (!map) {
                return;
            }

            anchorMarker._lahdPropertySync = syncLahdPropertyPresentation;
            map.on("zoomend", anchorMarker._lahdPropertySync);
            map.on("moveend", anchorMarker._lahdPropertySync);
            syncLahdPropertyPresentation();
        });

        anchorMarker.on("remove", function() {
            const map = anchorMarker._map;

            if (map && anchorMarker._lahdPropertySync) {
                map.off("zoomend", anchorMarker._lahdPropertySync);
                map.off("moveend", anchorMarker._lahdPropertySync);
            }

            if (anchorMarker._lahdPropertyHeatLayer) {
                if (map && map.hasLayer(anchorMarker._lahdPropertyHeatLayer)) {
                    map.removeLayer(anchorMarker._lahdPropertyHeatLayer);
                }
                anchorMarker._lahdPropertyHeatLayer = null;
            }

            if (map) {
                hideMarkerLayer(map);
                removeLegend(map);
            }
            anchorMarker._lahdPropertyMarkerLayer = null;
            anchorMarker._lahdPropertyLegendControl = null;
            anchorMarker._lahdPropertyLegendContainer = null;
            anchorMarker._lahdPropertySync = null;
        });

        return anchorMarker;
    }

    registerLayerRenderer("drawLahdPropertyHeatLayer", drawLahdPropertyHeatLayer);
})();
