window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, layer, context) {
            if (feature.properties.city) {
                layer.bindTooltip(`${feature.properties.city} (${feature.properties.density})`)
            }
        },
        function1: function(feature, latlng, context) {
            const {
                min,
                max,
                colorscale,
                circleOptions,
                colorProp
            } = context.hideout;
            const csc = chroma.scale(colorscale).domain([min, max]);
            circleOptions.fillColor = csc(feature.properties[colorProp]);
            return L.circleMarker(latlng, circleOptions);
        },
        function2: function(feature, latlng, index, context) {
            const {
                min,
                max,
                colorscale,
                circleOptions,
                colorProp
            } = context.hideout;
            const csc = chroma.scale(colorscale).domain([min, max]);

            // Access the leaves of the cluster
            const leaves = index.getLeaves(feature.properties.cluster_id);

            // Collect coordinates and sum property values
            let features = [];
            let valueSum = 0;

            for (let i = 0; i < leaves.length; ++i) {
                const coords = leaves[i].geometry.coordinates;
                const lng = coords[0];
                const lat = coords[1];

                // Create a Turf.js point feature
                features.push(turf.point([lng, lat]));

                // Sum the property values
                valueSum += leaves[i].properties[colorProp];
            }

            // Calculate the mean value for color scaling
            const valueMean = valueSum / leaves.length;

            // Create a Turf.js feature collection
            const fc = turf.featureCollection(features);

            // Compute the convex hull
            const convexHull = turf.convex(fc);

            // Create a Leaflet layer for the convex hull polygon
            let polygonLayer = null;
            if (convexHull) {
                polygonLayer = L.geoJSON(convexHull, {
                    style: {
                        color: csc(valueMean),
                        weight: 1,
                        fillOpacity: 0.2
                    }
                });
            } else {
                // If convex hull couldn't be computed (e.g., less than 3 points), create a circle
                polygonLayer = L.circle(latlng, {
                    radius: 50000, // Adjust radius as needed
                    color: csc(valueMean),
                    weight: 1,
                    fillOpacity: 0.2
                });
            }

            // Customize the cluster icon
            const scatterIcon = L.DivIcon.extend({
                createIcon: function(oldIcon) {
                    let icon = L.DivIcon.prototype.createIcon.call(this, oldIcon);
                    icon.style.backgroundColor = this.options.color;
                    return icon;
                }
            });

            const icon = new scatterIcon({
                html: '<div style="background-color:white;"><span>' + feature.properties.point_count_abbreviated + '</span></div>',
                className: "marker-cluster",
                iconSize: L.point(40, 40),
                color: csc(valueMean)
            });

            const marker = L.marker(latlng, {
                icon: icon
            });

            // Create a layer group containing the polygon and the marker
            const clusterLayer = L.layerGroup([polygonLayer, marker]);

            return clusterLayer;
        }
    }
});