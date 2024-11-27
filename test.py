import dash_leaflet as dl
from dash_extensions.javascript import assign
from dash import Dash

# External scripts
chroma = "https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js"
turf = "https://cdnjs.cloudflare.com/ajax/libs/Turf.js/6.5.0/turf.min.js"

# Color scale and properties
colorscale = ['red', 'yellow', 'green', 'blue', 'purple']
color_prop = 'density'
vmin = 0
vmax = 1000

# Create a colorbar
colorbar = dl.Colorbar(
    colorscale=colorscale,
    width=20,
    height=150,
    min=vmin,
    max=vmax,
    unit='/km2'
)

# JavaScript functions
on_each_feature = assign("""function(feature, layer, context){
    if(feature.properties.city){
        layer.bindTooltip(`${feature.properties.city} (${feature.properties.density})`)
    }
}""")

point_to_layer = assign("""function(feature, latlng, context){
    const {min, max, colorscale, circleOptions, colorProp} = context.hideout;
    const csc = chroma.scale(colorscale).domain([min, max]);
    circleOptions.fillColor = csc(feature.properties[colorProp]);
    return L.circleMarker(latlng, circleOptions);
}""")

cluster_to_layer = assign("""function(feature, latlng, index, context){
    const {min, max, colorscale, circleOptions, colorProp} = context.hideout;
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
            radius: 50000,  // Adjust radius as needed
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

    const marker = L.marker(latlng, {icon: icon});

    // Create a layer group containing the polygon and the marker
    const clusterLayer = L.layerGroup([polygonLayer, marker]);

    return clusterLayer;
}""")

# Create the GeoJSON layer
geojson = dl.GeoJSON(
    url="/assets/us-cities.json",
    cluster=True,
    zoomToBounds=True,
    pointToLayer=point_to_layer,
    onEachFeature=on_each_feature,
    clusterToLayer=cluster_to_layer,
    zoomToBoundsOnClick=True,
    superClusterOptions=dict(radius=150),
    hideout=dict(
        colorProp=color_prop,
        circleOptions=dict(fillOpacity=1, stroke=False, radius=5),
        min=vmin,
        max=vmax,
        colorscale=colorscale
    )
)

# Create the app
app = Dash(external_scripts=[chroma, turf], prevent_initial_callbacks=True)
app.layout = dl.Map(
    [dl.TileLayer(), geojson, colorbar],
    center=[37.0902, -95.7129],  # Center of the US
    zoom=4,
    style={'height': '100vh'}
)

if __name__ == '__main__':
    app.run_server()
