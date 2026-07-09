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
     * Build a subtle convex hull around oil-well cluster leaves.
     *
     * @param {{ properties?: Record<string, unknown> }} clusterFeature Cluster feature from Supercluster.
     * @param {any} index Cluster index passed by Dash Leaflet.
     * @returns {L.GeoJSON|null} Convex hull layer or `null`.
     */
    function buildOilClusterHull(clusterFeature, index) {
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
                color: "#7b4b24",
                weight: 2,
                opacity: 0.9,
                dashArray: "6 4",
                fillColor: "#c98b2e",
                fillOpacity: 0.1,
            },
        });
    }

    /**
     * Render oil-well clusters with a custom marker and hover hull.
     *
     * @param {{ properties?: Record<string, unknown> }} feature Cluster feature.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by Dash Leaflet.
     * @param {any} index Supercluster index.
     * @param {Record<string, unknown>} context Dash Leaflet runtime context.
     * @returns {L.Marker} Cluster marker configured for oil-well points.
     */
    function drawOilCluster(feature, latlng, index, context) {
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
                className: "oil-cluster-div-icon",
                html: `
                    <div class="oil-cluster-marker" aria-hidden="true">
                        <img class="oil-cluster-marker__icon" src="/assets/oil_derrick_icon.png" alt="" />
                        <span class="oil-cluster-marker__count">${countLabel}</span>
                    </div>
                `,
                iconSize: [74, 36],
                iconAnchor: [37, 18],
            }),
        });
        clusterMarker.feature = feature;

        function showHull() {
            if (context.currentPolygon) {
                context.map.removeLayer(context.currentPolygon);
            }

            const hullLayer = buildOilClusterHull(feature, index);
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

    registerLayerRenderer("drawOilCluster", drawOilCluster);
    registerLayerRenderer("drawOilIcon", drawOilIcon);
})();
