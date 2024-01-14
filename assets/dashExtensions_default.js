window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng) {
            const customIcon = L.icon({
                iconUrl: '/assets/oil_derrick_icon.png', // URL to your custom icon
                iconSize: [20, 20] // Adjust the size as needed
            });
            // Create a marker with this icon
            var marker = L.marker(latlng, {
                icon: customIcon
            });
            // Create a popup with feature properties
            //var popupContent = '<h4>Oil Derrick Info</h4>';
            //for (var key in feature.properties) {
            //    popupContent += key + ': ' + feature.properties[key] + '<br>';
            //}
            // Create a popup with specific feature properties
            var popupContent = '<h4>Oil Derrick Info</h4>';
            popupContent += 'Well Operator: ' + feature.properties.OperatorNa + '<br>';
            popupContent += 'API Number: ' + feature.properties.API + '<br>';
            popupContent += 'Well Type: ' + feature.properties.WellTypeLa + '<br>';
            popupContent += 'Lease Name: ' + feature.properties.LeaseName + '<br>';
            popupContent += 'Start Date: ' + feature.properties.SpudDate + '<br>';
            popupContent += 'Well Status: ' + feature.properties.WellStatus + '<br>';
            marker.bindPopup(popupContent);
            return marker;
        }
    }
});