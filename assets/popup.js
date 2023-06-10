// This is a JavaScript file to customize the Leaflet popup
// It should be used with dl.GeoJSON's `onEachFeature` option
// See https://github.com/perfectly-preserved-pie/larentals/issues/86#issuecomment-1585304809
window.dash_props = Object.assign({}, window.dash_props, {
    module: {
        on_each_feature: function(feature, layer, context) {
            if (!feature.properties) {
                return
            }
            if (feature.properties.popup) {
                layer.bindPopup(feature.properties.popup, {
                    // Here you can customize the popup
                    // https://leafletjs.com/reference.html#popup-option
                    autoPan: false,
                    closeButton: false,
                    // Set the maxHeight to 500px if the device is mobile, otherwise use the default value
                    maxHeight: window.innerWidth < 768 ? 500 : 650, 
                    // Set the maxWidth to 175px if the device is mobile, otherwise use the default value
                    maxWidth: window.innerWidth < 768 ? 175 : 300,
                })
            }
        }
    }
});