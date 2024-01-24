function militaryToStandard(time) {
    // Convert the time to a string if it's not already
    time = String(time);

    // Pad the time with zeros if it's less than 4 digits
    while (time.length < 4) {
        time = '0' + time;
    }

    var hours = parseInt(time.substring(0, 2));
    var minutes = parseInt(time.substring(2, 4));
    var suffix = hours >= 12 ? 'PM' : 'AM';

    // Convert to 12-hour time
    hours = ((hours + 11) % 12) + 1;

    return hours + ':' + minutes + ' ' + suffix;
}

window.myNamespace = Object.assign({}, window.myNamespace, {
    mySubNamespace: {
        drawOilIcon: function(feature, latlng) {
            const OilIcon = L.icon({
                iconUrl: '/assets/oil_derrick_icon.png',
                iconSize: [20, 20]  // Adjust the size as needed
            });
            var marker = L.marker(latlng, {icon: OilIcon});
            
            // Check if the required properties exist and create the popup content
            if (feature.properties) {
                var popupContent = '<h4>Oil/Gas Well Info</h4>';
                popupContent += 'API Number: ' + (feature.properties.API || 'N/A') + '<br>';
                popupContent += 'Lease Name: ' + (feature.properties.LeaseName || 'N/A') + '<br>';
                popupContent += 'Start Date: ' + (feature.properties.SpudDate || 'N/A') + '<br>';
                popupContent += 'Well Operator: ' + (feature.properties.OperatorNa || 'N/A') + '<br>';
                // Check the Well Status and set the color
                var wellStatus = feature.properties.WellStatus || 'N/A';
                var wellStatusColor = 'black';
                if (wellStatus === 'Plugged') {
                    wellStatusColor = 'green';
                } 
                else if (wellStatus === 'Active') {
                    wellStatusColor = 'red';
                } 
                else if (wellStatus === 'Idle') {
                    wellStatusColor = '#DAA520';  // Dark yellow
                }
                popupContent += 'Well Status: <span style="color:' + wellStatusColor + ';">' + wellStatus + '</span><br>';
                popupContent += 'Well Type: ' + (feature.properties.WellTypeLa || 'N/A') + '<br>';
                
                marker.bindPopup(popupContent);
            }

            return marker;
        },
        drawCrimeIcon: function(feature, latlng) {
            const CrimeIcon = L.icon({
                iconUrl: '/assets/crime_icon.png',
                iconSize: [25, 25]  // Adjust the size as needed
            });
            var marker = L.marker(latlng, {icon: CrimeIcon});
        
            // Check if the required properties exist and create the popup content
            if (feature.properties) {
                var popupContent = '<h4>Crime Info</h4>';
                popupContent += 'DR No: ' + (feature.properties.dr_no || 'N/A') + '<br>';
                popupContent += 'Date Occurred: ' + (feature.properties.date_occ.split('T')[0] || 'N/A') + '<br>';
                popupContent += 'Time Occurred: ' + (militaryToStandard(feature.properties.time_occ) || 'N/A') + '<br>';
                popupContent += 'Crime Code Description: ' + (feature.properties.crm_cd_desc || 'N/A') + '<br>';
                popupContent += 'Victim Age: ' + (feature.properties.vict_age || 'N/A') + '<br>';
                popupContent += 'Victim Sex: ' + (feature.properties.vict_sex || 'N/A') + '<br>';
                popupContent += 'Premise Description: ' + (feature.properties.premis_desc || 'N/A') + '<br>';
                popupContent += 'Weapon Description: ' + (feature.properties.weapon_desc || 'N/A') + '<br>';
                popupContent += 'Status Description: ' + (feature.properties.status_desc || 'N/A') + '<br>';
        
                marker.bindPopup(popupContent);
            }
        
            return marker;
        }
    }
});