(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupRuntime = popupApi && popupApi.runtime;
    const createPopupMarker = popupRuntime && popupRuntime.createPopupMarker;
    const registerLayerRenderer = popupRuntime && popupRuntime.registerLayerRenderer;

    if (typeof createPopupMarker !== "function" || typeof registerLayerRenderer !== "function") {
        console.error("Additional layer popup runtime did not load before the ALPR camera layer renderer.");
        return;
    }

    const FOV_DISTANCE_METERS = 150;
    const FOV_SPREAD_DEGREES = 50;
    const FOV_ARC_STEPS = 10;
    const EARTH_RADIUS_METERS = 6371000;
    const FOV_FILL_COLOR = "#f59e0b";
    const FOV_OUTLINE_COLOR = "#b42318";
    const CCTV_ICON_SVG = `
        <svg class="alpr-camera-cctv-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16.75 12h3.632a1 1 0 0 1 .894 1.447l-2.034 4.069a1 1 0 0 1-1.708.134l-2.124-2.97m1.696-5.627a1 1 0 0 1 .447 1.341l-3.106 6.211a1 1 0 0 1-1.342.447L3.61 12.3a2.92 2.92 0 0 1-1.3-3.91L3.69 5.6a2.92 2.92 0 0 1 3.92-1.3zM2 19h3.76a2 2 0 0 0 1.8-1.1L9 15m-7 6v-4m5-8h.01"></path>
        </svg>
    `;

    /**
     * Normalize a direction value into a compass bearing.
     *
     * @param {unknown} value Direction value from feature properties.
     * @returns {number|null} Bearing in degrees clockwise from north.
     */
    function normalizeBearing(value) {
        const numberValue = Number(value);
        if (!Number.isFinite(numberValue)) {
            return null;
        }
        return ((numberValue % 360) + 360) % 360;
    }

    /**
     * Resolve all usable bearings for a camera feature.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature.
     * @returns {number[]} Unique bearings.
     */
    function getCameraBearings(feature) {
        const properties = feature && feature.properties || {};
        const bearings = [];
        const seen = new Set();

        /**
         * Add one bearing to the output list after normalizing and deduping it.
         *
         * @param {unknown} value Raw direction value from feature properties.
         * @returns {void}
         */
        const addBearing = function(value) {
            const bearing = normalizeBearing(value);
            if (bearing === null) {
                return;
            }
            const key = bearing.toFixed(3);
            if (!seen.has(key)) {
                seen.add(key);
                bearings.push(bearing);
            }
        };

        if (Array.isArray(properties.directions) && properties.directions.length) {
            properties.directions.forEach(addBearing);
        } else {
            addBearing(properties.direction);
        }

        return bearings;
    }

    /**
     * Project a point by bearing and distance using a spherical-earth model.
     *
     * @param {L.LatLng} origin Camera location.
     * @param {number} bearingDegrees Bearing in degrees clockwise from north.
     * @param {number} distanceMeters Distance to project.
     * @returns {[number, number]} Leaflet `[lat, lng]` coordinate.
     */
    function projectLatLng(origin, bearingDegrees, distanceMeters) {
        const angularDistance = distanceMeters / EARTH_RADIUS_METERS;
        const bearing = bearingDegrees * Math.PI / 180;
        const lat1 = origin.lat * Math.PI / 180;
        const lon1 = origin.lng * Math.PI / 180;

        const lat2 = Math.asin(
            Math.sin(lat1) * Math.cos(angularDistance) +
            Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing)
        );
        const lon2 = lon1 + Math.atan2(
            Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
            Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2)
        );

        return [lat2 * 180 / Math.PI, lon2 * 180 / Math.PI];
    }

    /**
     * Build approximate field-of-view layers for a camera bearing.
     *
     * @param {L.LatLng} latlng Camera location.
     * @param {number} bearing Bearing in degrees clockwise from north.
     * @returns {L.Layer[]} Non-interactive cone polygon and center bearing line.
     */
    function buildFovConeLayers(latlng, bearing) {
        const points = [[latlng.lat, latlng.lng]];
        const start = bearing - FOV_SPREAD_DEGREES / 2;
        for (let step = 0; step <= FOV_ARC_STEPS; step += 1) {
            const angle = start + (FOV_SPREAD_DEGREES * step / FOV_ARC_STEPS);
            points.push(projectLatLng(latlng, angle, FOV_DISTANCE_METERS));
        }
        points.push([latlng.lat, latlng.lng]);

        const polygon = L.polygon(points, {
            className: "alpr-camera-fov-cone",
            color: FOV_OUTLINE_COLOR,
            weight: 3,
            opacity: 0.95,
            fillColor: FOV_FILL_COLOR,
            fillOpacity: 0.42,
            interactive: false,
        });
        const centerLine = L.polyline(
            [
                [latlng.lat, latlng.lng],
                projectLatLng(latlng, bearing, FOV_DISTANCE_METERS),
            ],
            {
                className: "alpr-camera-fov-bearing",
                color: FOV_OUTLINE_COLOR,
                weight: 3,
                opacity: 0.9,
                dashArray: "7 5",
                interactive: false,
            }
        );

        return [polygon, centerLine];
    }

    /**
     * Bind hover/click FOV behavior to a camera marker.
     *
     * @param {L.Marker} marker Marker returned for the camera point.
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by Dash Leaflet.
     * @returns {void}
     */
    function bindFovPreview(marker, feature, latlng) {
        const bearings = getCameraBearings(feature);
        if (!bearings.length) {
            return;
        }

        const origin = L.latLng(latlng);
        let fovLayer = null;
        let popupOpen = false;

        /**
         * Add the camera FOV cone layer to the map when possible.
         *
         * @returns {void}
         */
        function showFov() {
            const map = marker._map;
            if (!map || fovLayer) {
                return;
            }

            const fovLayers = [];
            bearings.forEach(function(bearing) {
                buildFovConeLayers(origin, bearing).forEach(function(layer) {
                    fovLayers.push(layer);
                });
            });
            fovLayer = L.layerGroup(fovLayers);
            fovLayer.addTo(map);
            fovLayer.eachLayer(function(layer) {
                if (typeof layer.bringToBack === "function") {
                    layer.bringToBack();
                }
            });
        }

        /**
         * Remove the FOV cone unless the marker popup is still open.
         *
         * @returns {void}
         */
        function hideFov() {
            if (popupOpen) {
                return;
            }
            if (fovLayer && marker._map) {
                marker._map.removeLayer(fovLayer);
            }
            fovLayer = null;
        }

        marker.on("mouseover", showFov);
        marker.on("focus", showFov);
        marker.on("click", showFov);
        marker.on("popupopen", function() {
            popupOpen = true;
            showFov();
        });
        marker.on("mouseout", hideFov);
        marker.on("blur", hideFov);
        marker.on("popupclose", function() {
            popupOpen = false;
            hideFov();
        });
        marker.on("remove", function() {
            popupOpen = false;
            if (fovLayer && marker._map) {
                marker._map.removeLayer(fovLayer);
            }
            fovLayer = null;
        });
    }

    /**
     * Build a subtle convex hull around ALPR cluster leaves.
     *
     * @param {{ properties?: Record<string, unknown> }} clusterFeature Cluster feature from Supercluster.
     * @param {any} index Cluster index passed by Dash Leaflet.
     * @returns {L.GeoJSON|null} Convex hull layer or `null`.
     */
    function buildAlprClusterHull(clusterFeature, index) {
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
                color: "#20242a",
                weight: 2,
                opacity: 0.88,
                dashArray: "6 4",
                fillColor: "#f59e0b",
                fillOpacity: 0.12,
            },
        });
    }

    /**
     * Render clustered ALPR cameras with a compact count marker.
     *
     * @param {{ properties?: Record<string, unknown> }} feature Cluster feature.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by Dash Leaflet.
     * @param {any} index Supercluster index passed by Dash Leaflet.
     * @param {Record<string, unknown>} context Dash Leaflet runtime context.
     * @returns {L.Marker} Cluster marker configured for ALPR camera points.
     */
    function drawAlprCameraCluster(feature, latlng, index, context) {
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
            className: "alpr-camera-cluster-div-icon",
            html: `
                <div class="alpr-camera-cluster-marker" aria-hidden="true">
                        <span class="alpr-camera-cluster-marker__icon">
                            <span class="alpr-camera-cluster-marker__symbol">${CCTV_ICON_SVG}</span>
                        </span>
                        <span class="alpr-camera-cluster-marker__count">${countLabel}</span>
                    </div>
                `,
                iconSize: [76, 34],
                iconAnchor: [38, 17],
            }),
        });
        clusterMarker.feature = feature;

        /**
         * Add the cluster hull layer for the hovered/focused cluster.
         *
         * @returns {void}
         */
        function showHull() {
            if (context.currentPolygon) {
                context.map.removeLayer(context.currentPolygon);
            }

            const hullLayer = buildAlprClusterHull(feature, index);
            if (hullLayer) {
                hullLayer.addTo(context.map);
                context.currentPolygon = hullLayer;
            }
        }

        /**
         * Remove the active cluster hull layer.
         *
         * @returns {void}
         */
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
     * Create an ALPR camera marker and bind popup content.
     *
     * @param {{ properties?: Record<string, unknown> }} feature GeoJSON feature for the camera.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
     * @returns {L.Marker} Marker configured for the feature.
     */
    function drawAlprCameraIcon(feature, latlng) {
        const cameraIcon = L.divIcon({
            className: "alpr-camera-div-icon",
            html: `
                <div class="alpr-camera-marker" aria-hidden="true">
                    <span class="alpr-camera-marker__symbol">${CCTV_ICON_SVG}</span>
                </div>
            `,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
            popupAnchor: [0, -12],
        });

        const marker = createPopupMarker(
            feature,
            latlng,
            cameraIcon,
            "buildAlprCameraPopupContent"
        );
        bindFovPreview(marker, feature, latlng);
        return marker;
    }

    registerLayerRenderer("drawAlprCameraCluster", drawAlprCameraCluster);
    registerLayerRenderer("drawAlprCameraIcon", drawAlprCameraIcon);
})();
