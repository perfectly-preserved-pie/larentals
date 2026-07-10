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

    /**
     * Render clustered ALPR cameras with a compact count marker.
     *
     * @param {{ properties?: Record<string, unknown> }} feature Cluster feature.
     * @param {unknown} latlng Leaflet lat/lng argument supplied by Dash Leaflet.
     * @returns {L.Marker} Cluster marker configured for ALPR camera points.
     */
    function drawAlprCameraCluster(feature, latlng) {
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
                            <span class="alpr-camera-cluster-marker__lens"></span>
                        </span>
                        <span class="alpr-camera-cluster-marker__count">${countLabel}</span>
                    </div>
                `,
                iconSize: [76, 34],
                iconAnchor: [38, 17],
            }),
        });
        clusterMarker.feature = feature;
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
                    <span class="alpr-camera-marker__body">
                        <span class="alpr-camera-marker__lens"></span>
                    </span>
                </div>
            `,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
            popupAnchor: [0, -12],
        });

        return createPopupMarker(
            feature,
            latlng,
            cameraIcon,
            "buildAlprCameraPopupContent"
        );
    }

    registerLayerRenderer("drawAlprCameraCluster", drawAlprCameraCluster);
    registerLayerRenderer("drawAlprCameraIcon", drawAlprCameraIcon);
})();
