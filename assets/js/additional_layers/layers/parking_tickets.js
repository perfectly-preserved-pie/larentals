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
        console.error("Additional layer popup runtime did not load before the parking tickets layer renderer.");
        return;
    }

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
     * } & Record<string, unknown>} ParkingHeatPointProperties
     */

    /**
     * @typedef {[number, number, number]} HeatPointTuple
     */

    /**
    * @typedef {[number, number, number, number, number, string, number?]} MarkerPointTuple
     */

    /**
     * @typedef {{
     *   showHeat: boolean,
     *   showMarkers: boolean,
     * }} ParkingLegendOptions
     */

    /**
     * @typedef {[string, string, string | null]} ParkingLegendMarkerEntry
     */

    /**
     * Return the inclusive upper percentile threshold from a sorted count distribution.
     *
     * @param {number[]} counts Sorted positive citation counts.
     * @param {number} fraction Percentile fraction in the inclusive `(0, 1]` range.
     * @returns {number} Integer threshold for the requested percentile.
     */
    function pickPercentileThreshold(counts, fraction) {
        if (!Array.isArray(counts) || !counts.length) {
            return 0;
        }

        const clampedFraction = Math.min(1, Math.max(0, Number(fraction) || 0));
        const index = Math.min(
            counts.length - 1,
            Math.max(0, Math.ceil(clampedFraction * counts.length) - 1)
        );
        return Math.max(1, Math.round(Number(counts[index]) || 0));
    }

    /**
     * Round a citation count up to a label-friendly threshold.
     *
     * @param {number} value Candidate citation-count threshold.
     * @returns {number} Rounded-up threshold suitable for a legend label.
     */
    function roundUpToFriendlyCount(value) {
        const numericValue = Math.max(1, Math.round(Number(value) || 0));

        if (numericValue <= 25) {
            return Math.ceil(numericValue / 5) * 5;
        }
        if (numericValue <= 100) {
            return Math.ceil(numericValue / 10) * 10;
        }
        if (numericValue <= 500) {
            return Math.ceil(numericValue / 25) * 25;
        }
        if (numericValue <= 1000) {
            return Math.ceil(numericValue / 50) * 50;
        }
        return Math.ceil(numericValue / 100) * 100;
    }

    /**
     * Derive hybrid marker tiers that stay user-readable while isolating outliers.
     *
     * The first tiers use fixed yearly frequencies:
     * - monthly-ish: 12 per year
     * - weekly-ish: 52 per year
     * - several per week: 156 per year
     *
     * The highest tier is reserved for statistical outliers using the larger of:
     * - 520 citations/year (roughly 10 per week)
     * - the rounded 99th-percentile threshold in the current dataset
     *
     * @param {number[]} counts Positive citation counts.
     * @returns {number[]} Ascending integer thresholds for five marker tiers.
     */
    function deriveHybridMarkerBreaks(counts) {
        const sanitizedCounts = Array.isArray(counts)
            ? counts
                .map(function(value) {
                    return Number(value);
                })
                .filter(function(value) {
                    return Number.isFinite(value) && value > 0;
                })
                .sort(function(a, b) {
                    return a - b;
                })
            : [];

        const baselineBreaks = [12, 52, 156, 520];
        if (!sanitizedCounts.length) {
            return baselineBreaks;
        }

        const percentile99 = pickPercentileThreshold(sanitizedCounts, 0.99);
        const extremeThreshold = Math.max(
            baselineBreaks[3],
            roundUpToFriendlyCount(percentile99)
        );

        return [baselineBreaks[0], baselineBreaks[1], baselineBreaks[2], extremeThreshold];
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
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON anchor feature for the parking heatmap.
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
                const mergedGeocodeCount = Number(point[6] || 1);
                if (
                    !Number.isFinite(lat) ||
                    !Number.isFinite(lon) ||
                    !Number.isFinite(citationCount) ||
                    !Number.isFinite(totalFineAmount) ||
                    !Number.isFinite(averageFineAmount) ||
                    !Number.isFinite(mergedGeocodeCount) ||
                    !location
                ) {
                    return null;
                }

                return [lat, lon, citationCount, totalFineAmount, averageFineAmount, location, mergedGeocodeCount];
            })
            .filter(function(point) {
                return Array.isArray(point);
            });
        const popupBuilder = getPopupBuilder("buildParkingTicketsPopupContent");
        const markerZoomMin = Number(properties.marker_zoom_min) || 15;
        const heatZoomMax = Number(properties.heat_zoom_max) || 16;
        const maxCitationCount = Math.max(1, Number(properties.max_citation_count) || 1);
        const markerCitationCounts = markerPoints
            .map(function(point) {
                return Number(point[2]);
            })
            .filter(function(value) {
                return Number.isFinite(value) && value > 0;
            });
        const markerFrequencyBreaks = deriveHybridMarkerBreaks(markerCitationCounts);

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

        /**
         * Format citation counts for compact, readable legend labels.
         *
         * @param {unknown} value Candidate citation count.
         * @returns {string} Localized citation-count label.
         */
        function formatCitationCount(value) {
            const numericValue = Number(value);
            if (!Number.isFinite(numericValue)) {
                return "0";
            }

            return numericValue.toLocaleString("en-US");
        }

        /**
         * Lazily create the Leaflet legend control owned by this overlay instance.
         *
         * @param {L.Map} map Active Leaflet map.
         * @returns {L.Control} Legend control for the parking citations layer.
         */
        function ensureLegendControl(map) {
            void map;
            if (anchorMarker._parkingTicketsLegendControl) {
                return anchorMarker._parkingTicketsLegendControl;
            }

            anchorMarker._parkingTicketsLegendControl = L.control({ position: "topright" });
            anchorMarker._parkingTicketsLegendControl.onAdd = function() {
                const container = L.DomUtil.create(
                    "div",
                    "leaflet-control parking-tickets-legend"
                );
                container.innerHTML = "";
                container.style.minWidth = "208px";
                container.style.maxWidth = "240px";
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
                anchorMarker._parkingTicketsLegendContainer = container;
                return container;
            };

            return anchorMarker._parkingTicketsLegendControl;
        }

        /**
         * Rebuild the legend contents to match the current zoom presentation.
         *
         * @param {ParkingLegendOptions | null | undefined} options Current legend visibility state.
         * @returns {void}
         */
        /**
         * Renders a parking citations legend in the marker's container.
         * 
         * The legend displays:
         * - Heat intensity gradient: visual representation of ticket density (lower to higher)
         * - Street-level citations: five frequency tiers from occasional to extreme hotspots
         * - Time window: applicable date range for the citation data
         * 
         * @param {Object} options - Configuration options
         * @param {boolean} [options.showHeat] - Whether to display the heat map intensity guide
         * @param {boolean} [options.showMarkers] - Whether to display the hotspot frequency tiers
         */
        function renderLegend(options) {
            if (!anchorMarker._parkingTicketsLegendContainer) {
                return;
            }

            const showHeat = Boolean(options && options.showHeat);
            const showMarkers = Boolean(options && options.showMarkers);
            const tier2 = markerFrequencyBreaks[0] || 0;
            const tier3 = markerFrequencyBreaks[1] || 0;
            const tier4 = markerFrequencyBreaks[2] || 0;
            const tier5 = markerFrequencyBreaks[3] || 0;
            const windowLabel = [
                String(properties.window_start || "").trim(),
                String(properties.window_end || "").trim(),
            ]
                .filter(Boolean)
                .join(" to ");
            /** @type {string[]} */
            const legendSections = [];

            if (showHeat) {
                legendSections.push(
                    [
                        '<div class="parking-tickets-legend__section" style="margin-top: 10px;">',
                        '<div class="parking-tickets-legend__subtitle" style="margin-bottom: 6px; font-size: 0.78rem; font-weight: 600;">Heat intensity</div>',
                        '<div class="parking-tickets-legend__gradient" aria-hidden="true" style="height: 10px; border-radius: 999px; background: linear-gradient(90deg, #2748ff 0%, #00b6ff 22%, #19d889 46%, #ffe34d 68%, #ff9730 84%, #ff2f1f 100%);"></div>',
                        '<div class="parking-tickets-legend__range" style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 0.72rem; color: #556270;">',
                        "<span>Lower</span>",
                        "<span>Higher</span>",
                        "</div>",
                        "</div>",
                    ].join("")
                );
            }

            if (showMarkers) {
                /** @type {ParkingLegendMarkerEntry[]} */
                const markerLegendEntries = [
                    ['#3da1ff', 'Occasional', tier2 > 0 ? "< " + formatCitationCount(tier2) + "/year" : null],
                    ['#2ecf7f', 'Monthly', tier2 > 0 && tier3 > 0 ? formatCitationCount(tier2) + "\u2013" + formatCitationCount(tier3 - 1) + "/year" : null],
                    ['#ffd43b', 'Weekly', tier3 > 0 && tier4 > 0 ? formatCitationCount(tier3) + "\u2013" + formatCitationCount(tier4 - 1) + "/year" : null],
                    ['#ff8f1f', 'Several per week', tier4 > 0 && tier5 > 0 ? formatCitationCount(tier4) + "\u2013" + formatCitationCount(tier5 - 1) + "/year" : null],
                    ['#ff3123', 'Extreme Hotspot', tier5 > 0 ? formatCitationCount(tier5) + "+/year" : null],
                ];

                legendSections.push(
                    [
                        '<div class="parking-tickets-legend__section" style="margin-top: 10px;">',
                        '<div class="parking-tickets-legend__subtitle" style="margin-bottom: 6px; font-size: 0.78rem; font-weight: 600;">Street-level citations</div>',
                        '<div class="parking-tickets-legend__marker-list" style="display: grid; gap: 5px;">',
                        markerLegendEntries
                            .filter(function(item) {
                                return item[2];
                            })
                            .map(function(item) {
                                return [
                                    '<div class="parking-tickets-legend__marker-row" style="display: flex; align-items: center; gap: 8px; font-size: 0.74rem; line-height: 1.25;">',
                                    '<span class="parking-tickets-legend__marker-swatch" style="display: inline-block; width: 10px; height: 10px; flex: 0 0 10px; border: 1px solid rgba(15, 27, 38, 0.35); border-radius: 999px; background:',
                                    item[0],
                                    ';"></span>',
                                    '<span class="parking-tickets-legend__label" style="color: #1f2d3a;">',
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

            anchorMarker._parkingTicketsLegendContainer.innerHTML = [
                '<div class="parking-tickets-legend__title" style="font-size: 0.95rem; font-weight: 700; line-height: 1.2;">Parking citations</div>',
                windowLabel
                    ? '<div class="parking-tickets-legend__caption" style="margin-top: 2px; font-size: 0.72rem; color: #556270;">' + windowLabel + "</div>"
                    : "",
                legendSections.join(""),
                '<div class="parking-tickets-legend__hint" style="margin-top: 10px; font-size: 0.7rem; color: #556270;">Warmer colors mean more citations.</div>',
            ].join("");
        }

        /**
         * Ensure the legend control is mounted and refreshed for the active zoom state.
         *
         * @param {L.Map} map Active Leaflet map.
         * @param {ParkingLegendOptions} options Current legend visibility state.
         * @returns {void}
         */
        function syncLegend(map, options) {
            const legendControl = ensureLegendControl(map);
            if (!map.hasLayer || typeof map.hasLayer !== "function") {
                return;
            }

            if (!map._controlCorners || !map._controlContainer) {
                return;
            }

            if (!map._parkingTicketsLegendMounted) {
                legendControl.addTo(map);
                map._parkingTicketsLegendMounted = true;
            }

            renderLegend(options);
        }

        /**
         * Remove the parking legend when the overlay is unmounted.
         *
         * @param {L.Map | null | undefined} map Active Leaflet map, when still attached.
         * @returns {void}
         */
        function removeLegend(map) {
            if (
                map &&
                anchorMarker._parkingTicketsLegendControl &&
                map._parkingTicketsLegendMounted
            ) {
                anchorMarker._parkingTicketsLegendControl.remove();
                map._parkingTicketsLegendMounted = false;
            }

            anchorMarker._parkingTicketsLegendContainer = null;
        }

        function ensureParkingTicketsMarkerPane(map) {
            if (!map.getPane("parkingTicketsMarkerPane")) {
                const markerPane = map.createPane("parkingTicketsMarkerPane");
                markerPane.style.zIndex = "610";
            }
        }

        function buildMarkerStyle(citationCount) {
            const normalizedCount = Math.sqrt(citationCount / maxCitationCount);
            const tier2 = markerFrequencyBreaks[0] || 0;
            const tier3 = markerFrequencyBreaks[1] || 0;
            const tier4 = markerFrequencyBreaks[2] || 0;
            const tier5 = markerFrequencyBreaks[3] || 0;

            let fillColor = "#3da1ff";
            let strokeColor = "#0f1b26";

            if (citationCount >= tier5 && tier5 > 0) {
                fillColor = "#ff3123";
                strokeColor = "#4f0a06";
            } else if (citationCount >= tier4 && tier4 > 0) {
                fillColor = "#ff8f1f";
                strokeColor = "#5c2d00";
            } else if (citationCount >= tier3 && tier3 > 0) {
                fillColor = "#ffd43b";
                strokeColor = "#665200";
            } else if (citationCount >= tier2 && tier2 > 0) {
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
                    merged_geocode_count: point[6],
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
            syncLegend(map, { showHeat: showHeat, showMarkers: showMarkers });

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
                removeLegend(map);
            }
            anchorMarker._parkingTicketsMarkerLayer = null;
            anchorMarker._parkingTicketsLegendControl = null;
            anchorMarker._parkingTicketsLegendContainer = null;
            anchorMarker._parkingTicketsSync = null;
        });

        return anchorMarker;
    }

    registerLayerRenderer("drawParkingHeatLayer", drawParkingHeatLayer);
})();
