window.myNamespace = Object.assign({}, window.myNamespace, {
    mySubNamespace: {
        drawCustomIcon: function(feature, latlng) {
            const customIcon = L.icon({
                iconUrl: '/assets/oil_derrick_icon.png',
                iconSize: [20, 20]  // Adjust the size as needed
            });
            var marker = L.marker(latlng, {icon: customIcon});
            
            // Check if the required properties exist and create the popup content
            if (feature.properties) {
                var popupContent = '<h4>Oil Derrick Info</h4>';
                popupContent += 'Well Operator: ' + (feature.properties.OperatorNa || 'N/A') + '<br>';
                popupContent += 'API Number: ' + (feature.properties.API || 'N/A') + '<br>';
                popupContent += 'Well Type: ' + (feature.properties.WellTypeLa || 'N/A') + '<br>';
                popupContent += 'Lease Name: ' + (feature.properties.LeaseName || 'N/A') + '<br>';
                popupContent += 'Start Date: ' + (feature.properties.SpudDate || 'N/A') + '<br>';
                popupContent += 'Well Status: ' + (feature.properties.WellStatus || 'N/A') + '<br>';
                
                marker.bindPopup(popupContent);
            }

            return marker;
        }
    }
});