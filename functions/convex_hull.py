from dash_extensions.javascript import assign

generate_convex_hulls = assign("""function(feature, latlng, index, context){
    // A global reference to the currently displayed polygon
    if (!context.currentPolygon) {
        context.currentPolygon = null;
    }

    // Access all the leaves of the cluster
    const leaves = index.getLeaves(feature.properties.cluster_id, Infinity); // Retrieve all children
    const clusterSize = leaves.length;

    // Define a color scale (mimicking Leaflet.markercluster behavior)
    // Default colors are at https://github.com/Leaflet/Leaflet.markercluster/blob/master/dist/MarkerCluster.Default.css
    // Because I'm coloring the polygons (instead of using the default blue) most of the default colors look way too faint on the map
    // So I'm adjusting them here           
    const getColor = function(size) {
        if (size < 50) return 'rgba(110, 204, 57, 0.6)';   // Small clusters
        if (size < 200) return 'yellow';                   // Medium clusters
        if (size < 500) return 'orange';                   // Larger clusters
        return 'red';                                      // Very large clusters
    };         

    // Get the appropriate color for the cluster size
    const color = getColor(clusterSize);

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
                color: color,     // Use the same color as the cluster icon
                weight: 2,        // Border thickness
                fillOpacity: 0.2, // Polygon fill transparency
                fillColor: color  // Polygon fill color
            }
        });
    }

    // Create a custom marker for the cluster with Leaflet.markercluster font styling
    const clusterMarker = L.marker(latlng, {
        icon: L.divIcon({
            html: `
                <div style="position:relative; width:40px; height:40px; font-family: Arial, sans-serif; font-size: 12px;">
                    <div style="background-color:${color}; opacity:0.6; 
                                border-radius:50%; width:40px; height:40px; 
                                position:absolute; top:0; left:0;"></div>
                    <div style="background-color:${color}; 
                                border-radius:50%; width:30px; height:30px; 
                                position:absolute; top:5px; left:5px; 
                                display:flex; align-items:center; justify-content:center; 
                                font-weight:normal; color:black; font-size:12px; font-family: Arial, sans-serif;">
                        ${feature.properties.point_count_abbreviated}
                    </div>
                </div>`,
            className: 'marker-cluster',
            iconSize: L.point(40, 40)    // Adjust the icon size
        })
    });

    // Don't show a popup when a cluster is clicked
    clusterMarker.on('click', function(e) {
        // Stop event propagation to prevent popup
        L.DomEvent.stopPropagation(e);
        
        // Remove any existing popup
        if (clusterMarker.getPopup()) {
            clusterMarker.unbindPopup();
        }
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

    // Add behavior to remove the polygon when the mouse leaves the cluster
    clusterMarker.on('mouseout', function() {
        if (context.currentPolygon) {
            context.map.removeLayer(context.currentPolygon);
            context.currentPolygon = null;
        }
    });

    return clusterMarker;
}""")