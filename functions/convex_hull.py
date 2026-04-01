from dash_extensions.javascript import assign

generate_convex_hulls = assign("""function(feature, latlng, index, context){
    // A global reference to the currently displayed polygon
    if (!context.currentPolygon) {
        context.currentPolygon = null;
    }
    window.larentals = window.larentals || {};

    // Access all the leaves of the cluster
    const leaves = index.getLeaves(feature.properties.cluster_id, Infinity); // Retrieve all children
    const clusterSize = leaves.length;

    // Single neutral color for all clusters
    //const color = 'rgba(100, 149, 237, 0.85)';  // Cornflower blue, higher opacity for visibility
    const color = 'rgba(23, 162, 184, 0.9)';  // Bootstrap info color - crisp, professional
                               
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
    
    // Scale marker opacity based on cluster density
    // Larger clusters = higher opacity for visual prominence
    const getMarkerOpacity = function(size) {
        const minOpacity = 0.5;
        const maxOpacity = 0.85;
        const minCluster = 10;
        const maxCluster = 10000;
        
        // Logarithmic scale matching size scaling
        const logSize = Math.log(size);
        const logMin = Math.log(minCluster);
        const logMax = Math.log(maxCluster);
        
        const normalized = (logSize - logMin) / (logMax - logMin);
        const opacity = minOpacity + (normalized * (maxOpacity - minOpacity));
        
        return Math.min(Math.max(opacity, minOpacity), maxOpacity);
    };
    
    const markerSize = getMarkerSize(clusterSize);
    const markerOpacity = getMarkerOpacity(clusterSize);
    const innerSize = markerSize * 0.75; // Inner circle is 75% of outer circle

    const buildPolygonLayer = function(clusterFeature) {
        const clusterId = clusterFeature?.properties?.cluster_id;
        if (clusterId === undefined || clusterId === null) {
            return null;
        }

        const clusterLeaves = index.getLeaves(clusterId, Infinity);
        const hullFeatures = [];
        for (let i = 0; i < clusterLeaves.length; ++i) {
            const coords = clusterLeaves[i]?.geometry?.coordinates;
            if (!Array.isArray(coords) || coords.length < 2) continue;
            hullFeatures.push(turf.point([coords[0], coords[1]]));
        }

        if (hullFeatures.length < 3) {
            return null;
        }

        const fc = turf.featureCollection(hullFeatures);
        const convexHull = turf.convex(fc);
        if (!convexHull) {
            return null;
        }

        return L.geoJSON(convexHull, {
            style: {
                color: color,
                weight: 2,
                fillOpacity: 0.2,
                fillColor: color
            }
        });
    };

    // Create a custom marker with size and opacity varying by density
    const clusterMarker = L.marker(latlng, {
        icon: L.divIcon({
            html: `
                <div style="position:relative; width:${markerSize}px; height:${markerSize}px; font-family: Arial, sans-serif;">
                    <div style="background-color:${color}; opacity:${markerOpacity}; 
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
    clusterMarker.feature = feature;

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
        const polygonLayer = buildPolygonLayer(clusterMarker.feature || feature);
        if (polygonLayer) {
            polygonLayer.addTo(context.map);
            context.currentPolygon = polygonLayer;
            window.larentals.currentConvexHull = polygonLayer;
            window.larentals.currentConvexHullMap = context.map;
        }
    });

    // Add behavior to remove the polygon when the mouse leaves the cluster
    clusterMarker.on('mouseout', function() {
        if (context.currentPolygon) {
            context.map.removeLayer(context.currentPolygon);
            context.currentPolygon = null;
        }
        window.larentals.currentConvexHull = null;
        window.larentals.currentConvexHullMap = null;
    });

    clusterMarker.on('remove', function() {
        if (context.currentPolygon) {
            context.map.removeLayer(context.currentPolygon);
            context.currentPolygon = null;
        }
        window.larentals.currentConvexHull = null;
        window.larentals.currentConvexHullMap = null;
    });

    return clusterMarker;
}""")
