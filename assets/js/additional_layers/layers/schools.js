(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (typeof createPopupMarker !== "function" || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the schools layer renderer.");
        return;
    }

    /**
     * Resolve a marker color chip class from the school level.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} CSS class for the marker chip.
     */
    function resolveSchoolMarkerClass(properties) {
        const level = String(properties && properties.school_level || "").toLowerCase();

        if (level.includes("elementary")) {
            return "school-marker__chip school-marker__chip--elementary";
        }
        if (level.includes("middle")) {
            return "school-marker__chip school-marker__chip--middle";
        }
        if (level.includes("high") || level.includes("secondary")) {
            return "school-marker__chip school-marker__chip--high";
        }
        return "school-marker__chip school-marker__chip--other";
    }

    /**
     * Build a subtle convex hull around school-cluster leaves.
     *
     * @param {{ properties?: Record<string, unknown> }} clusterFeature Cluster feature from Supercluster.
     * @param {any} index Cluster index passed by Dash Leaflet.
     * @returns {L.GeoJSON|null} Convex hull layer or `null`.
     */
    function buildSchoolClusterHull(clusterFeature, index) {
        const clusterId = clusterFeature && clusterFeature.properties && clusterFeature.properties.cluster_id;
        if (clusterId === null || clusterId === undefined || !index || typeof index.getLeaves !== "function") {
            return null;
        }

        const clusterLeaves = index.getLeaves(clusterId, Infinity) || [];
        if (clusterLeaves.length < 3 || typeof turf === "undefined") {
            return null;
        }

        const hullPoints = clusterLeaves
            .map(function(leaf) {
                const coords = leaf && leaf.geometry && leaf.geometry.coordinates;
                if (!Array.isArray(coords) || coords.length < 2) {
                    return null;
                }
                return turf.point([coords[0], coords[1]]);
            })
            .filter(Boolean);

        if (hullPoints.length < 3) {
            return null;
        }

        const hull = turf.convex(turf.featureCollection(hullPoints));
        if (!hull) {
            return null;
        }

        return L.geoJSON(hull, {
            interactive: false,
            style: {
                color: "#1d6f8d",
                weight: 2,
                opacity: 0.9,
                dashArray: "6 4",
                fillColor: "#2d8f5b",
                fillOpacity: 0.08,
            },
        });
    }

    /**
     * Render school clusters with a distinct pill-shaped icon and hover hull.
     *
     * @param {{ properties?: Record<string, unknown> }} feature Cluster feature.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by Dash Leaflet.
     * @param {any} index Supercluster index.
     * @param {Record<string, unknown>} context Dash Leaflet runtime context.
     * @returns {L.Marker} Cluster marker configured for school points.
     */
    function drawSchoolCluster(feature, latlng, index, context) {
        if (!context.currentPolygon) {
            context.currentPolygon = null;
        }

        const countLabel = String(
            feature && feature.properties && (
                feature.properties.point_count_abbreviated ||
                feature.properties.point_count ||
                ""
            )
        );
        const clusterMarker = L.marker(latlng, {
            icon: L.divIcon({
                className: "school-cluster-div-icon",
                html: `
                    <div class="school-cluster-marker" aria-hidden="true">
                        <span class="school-cluster-marker__icon">🏫</span>
                        <span class="school-cluster-marker__count">${countLabel}</span>
                    </div>
                `,
                iconSize: [72, 36],
                iconAnchor: [36, 18],
            }),
        });
        clusterMarker.feature = feature;

        function showHull() {
            if (context.currentPolygon) {
                context.map.removeLayer(context.currentPolygon);
            }

            const hullLayer = buildSchoolClusterHull(feature, index);
            if (hullLayer) {
                hullLayer.addTo(context.map);
                context.currentPolygon = hullLayer;
            }
        }

        function hideHull() {
            if (context.currentPolygon) {
                context.map.removeLayer(context.currentPolygon);
                context.currentPolygon = null;
            }
        }

        clusterMarker.on("mouseover", showHull);
        clusterMarker.on("focus", showHull);
        clusterMarker.on("mouseout", hideHull);
        clusterMarker.on("blur", hideHull);

        clusterMarker.on("remove", function() {
            hideHull();
        });

        return clusterMarker;
    }

    /**
     * Create the school marker and bind popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the school.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawSchoolIcon(feature, latlng) {
        const schoolIcon = L.divIcon({
            className: "school-div-icon",
            html: `
                <div class="${resolveSchoolMarkerClass(feature && feature.properties || {})}">
                    <span class="school-marker__symbol">🏫</span>
                </div>
            `,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
            popupAnchor: [0, -12],
        });

        return createPopupMarker(
            feature,
            latlng,
            schoolIcon,
            "buildSchoolPopupContent",
            {
                maxWidth: 460,
                minWidth: 340,
            }
        );
    }

    registerLayerRenderer("drawSchoolIcon", drawSchoolIcon);
    registerLayerRenderer("drawSchoolCluster", drawSchoolCluster);
})();
