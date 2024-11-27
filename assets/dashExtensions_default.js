window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng, index, context) {
            // A global reference to the currently displayed polygon
            if (!context.currentPolygon) {
                context.currentPolygon = null;
            }

            // Access all the leaves of the cluster
            const leaves = index.getLeaves(feature.properties.cluster_id, Infinity); // Retrieve all children

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

            // If the convex hull exists, create it as a polygon
            let polygonLayer = null;
            if (convexHull) {
                polygonLayer = L.geoJSON(convexHull, {
                    style: {
                        color: '#3388ff', // Border color
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

            // Add mouseover behavior to display the convex hull
            clusterMarker.on('mouseover', function() {
                // Remove the previously displayed polygon, if any
                if (context.currentPolygon) {
                    context.map.removeLayer(context.currentPolygon);
                }

                // Add the new polygon to the map and update the reference
                if (polygonLayer) {
                    polygonLayer.addTo(context.map);
                    context.currentPolygon = polygonLayer;
                }
            });

            // Add behavior to remove the polygon when the cluster is clicked or no longer needed
            clusterMarker.on('mouseout', function() {
                if (context.currentPolygon) {
                    context.map.removeLayer(context.currentPolygon);
                    context.currentPolygon = null;
                }
            });

            return clusterMarker;
        }
    }
});