from dash_extensions.javascript import assign

generate_convex_hulls = assign("""function(feature, latlng, index, context){
    // A global reference to the currently displayed polygon
    if (!context.currentPolygon) {
        context.currentPolygon = null;
    }

    // Access all the leaves of the cluster
    const leaves = index.getLeaves(feature.properties.cluster_id, Infinity); // Retrieve all children
    const clusterSize = leaves.length;

    // Single neutral color for all clusters
    const color = 'rgba(100, 149, 237, 0.85)';  // Cornflower blue, higher opacity for visibility
    
    // Scale marker size based on cluster density instead of color
    // Larger clusters = physically bigger markers
    // Use logarithmic scaling for better distribution across all cluster sizes
    const getMarkerSize = function(size) {
        const minSize = 40;
        const maxSize = 80;
        const minCluster = 10;
        const maxCluster = 10000; // Adjust based on max cluster size
        
        // Logarithmic scale
        const logSize = Math.log(size);
        const logMin = Math.log(minCluster);
        const logMax = Math.log(maxCluster);
        
        const normalized = (logSize - logMin) / (logMax - logMin);
        const markerSize = minSize + (normalized * (maxSize - minSize));
        
        return Math.min(Math.max(markerSize, minSize), maxSize);
    };
    
    const markerSize = getMarkerSize(clusterSize);
    const innerSize = markerSize * 0.75; // Inner circle is 75% of outer circle

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
                color: color,
                weight: 2,
                fillOpacity: 0.2,
                fillColor: color
            }
        });
    }

    // Create a custom marker with size varying by density
    const clusterMarker = L.marker(latlng, {
        icon: L.divIcon({
            html: `
                <div style="position:relative; width:${markerSize}px; height:${markerSize}px; font-family: Arial, sans-serif;">
                    <div style="background-color:${color}; opacity:0.6; 
                                border-radius:50%; width:${markerSize}px; height:${markerSize}px; 
                                position:absolute; top:0; left:0;"></div>
                    <div style="background-color:${color}; 
                                border-radius:50%; width:${innerSize}px; height:${innerSize}px; 
                                position:absolute; top:${(markerSize - innerSize) / 2}px; left:${(markerSize - innerSize) / 2}px; 
                                display:flex; align-items:center; justify-content:center; 
                                font-weight:bold; color:white; font-size:${Math.floor(innerSize / 2.5)}px;">
                        ${feature.properties.point_count_abbreviated}
                    </div>
                </div>`,
            className: 'marker-cluster',
            iconSize: L.point(markerSize, markerSize)
        })
    });

    // Don't show a popup when a cluster is clicked
    clusterMarker.on('click', function(e) {
        L.DomEvent.stopPropagation(e);
        if (clusterMarker.getPopup()) {
            clusterMarker.unbindPopup();
        }
    });

    // Add mouseover behavior to display the convex hull
    clusterMarker.on('mouseover', function() {
        if (context.currentPolygon) {
            context.map.removeLayer(context.currentPolygon);
        }
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