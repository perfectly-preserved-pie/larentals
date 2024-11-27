window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng, index, context) {
            // Access the leaves of the cluster
            const leaves = index.getLeaves(feature.properties.cluster_id);

            // Collect coordinates for the cluster's children
            let features = [];
            for (let i = 0; i < leaves.length; ++i) {
                const coords = leaves[i].geometry.coordinates;
                const lng = coords[0];
                const lat = coords[1];
                features.push(turf.point([lng, lat]));
            }

            // Create a Turf.js feature collection
            const fc = turf.featureCollection(features);

            // Compute the convex hull
            const convexHull = turf.convex(fc);

            // If the convex hull exists, render it as a polygon
            let polygonLayer = null;
            if (convexHull) {
                polygonLayer = L.geoJSON(convexHull, {
                    style: {
                        color: '#3388ff', // Border color (default Leaflet cluster color)
                        weight: 2, // Border thickness
                        fillOpacity: 0.2, // Polygon fill transparency
                        fillColor: '#3388ff' // Polygon fill color
                    }
                });
            }

            // Create a custom marker for the cluster
            const clusterMarker = L.marker(latlng, {
                icon: L.divIcon({
                    html: '<div style="background-color:rgba(51, 136, 255, 0.8); border-radius:50%; width:30px; height:30px; display:flex; align-items:center; justify-content:center; color:white;">' +
                        feature.properties.point_count_abbreviated + '</div>',
                    className: 'cluster-marker',
                    iconSize: L.point(30, 30)
                })
            });

            // Show the convex hull on hover
            clusterMarker.on('mouseover', function() {
                if (polygonLayer) polygonLayer.addTo(context.map);
            });

            // Hide the convex hull when the hover ends
            clusterMarker.on('mouseout', function() {
                if (polygonLayer) context.map.removeLayer(polygonLayer);
            });

            return clusterMarker;
        }
    }
});