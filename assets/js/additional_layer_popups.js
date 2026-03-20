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

    // Pad the minutes with a leading zero if they're less than 10
    minutes = minutes < 10 ? '0' + minutes : minutes;

    return hours + ':' + minutes + ' ' + suffix;
}

function isBlankValue(value) {
    if (value === null || value === undefined) {
        return true;
    }

    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        return normalized === '' || normalized === 'null' || normalized === 'none' || normalized === 'nan';
    }

    return false;
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatPropertyLabel(key) {
    const labels = {
        OBJECTID: 'Object ID',
        OBJECTID_1: 'Object ID 1',
        POINT_X: 'Point X',
        POINT_Y: 'Point Y',
        addrln1: 'Address Line 1',
        addrln2: 'Address Line 2',
        allcats: 'All Categories',
        cat1: 'Category 1',
        cat2: 'Category 2',
        cat3: 'Category 3',
        date_updated: 'Date Updated',
        dis_status: 'Display Status',
        ext_id: 'External ID',
        info1: 'Info 1',
        info2: 'Info 2',
        isCounty: 'County Market',
        nameUrlFriendly: 'URL Friendly Name',
        org_name: 'Organization',
        phones: 'Phone',
        post_id: 'Post ID',
        use_type: 'Use Type'
    };

    if (labels[key]) {
        return labels[key];
    }

    return key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, function(char) {
            return char.toUpperCase();
        });
}

function formatFarmersMarketValue(key, value) {
    if (isBlankValue(value)) {
        return 'N/A';
    }

    const valueAsString = String(value).trim();

    if ((key === 'url' || key === 'link') && /^https?:\/\//i.test(valueAsString)) {
        const safeUrl = escapeHtml(valueAsString);
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeUrl}</a>`;
    }

    if (key === 'email') {
        const safeEmail = escapeHtml(valueAsString);
        return `<a href="mailto:${safeEmail}">${safeEmail}</a>`;
    }

    if (key === 'isCounty') {
        return Number(value) === 1 ? 'Yes' : 'No';
    }

    return escapeHtml(valueAsString);
}

function joinAddressParts(parts) {
    return parts
        .filter(function(part) {
            return !isBlankValue(part);
        })
        .map(function(part) {
            return String(part).trim();
        })
        .join(', ');
}

function buildFarmersMarketAddress(properties) {
    const street = joinAddressParts([properties.addrln1, properties.addrln2]);
    const cityStateZip = joinAddressParts([properties.city, properties.state, properties.zip]);

    if (!street && !cityStateZip) {
        return 'N/A';
    }
    if (!street) {
        return escapeHtml(cityStateZip);
    }
    if (!cityStateZip) {
        return escapeHtml(street);
    }
    return escapeHtml(`${street}, ${cityStateZip}`);
}

function buildFarmersMarketWebsite(properties) {
    const url = isBlankValue(properties.url) ? null : String(properties.url).trim();
    const link = isBlankValue(properties.link) ? null : String(properties.link).trim();
    const candidates = [];

    if (url) {
        candidates.push(url);
    }
    if (link && link !== url) {
        candidates.push(link);
    }
    if (candidates.length === 0) {
        return 'N/A';
    }

    return candidates
        .map(function(candidate) {
            const safeUrl = escapeHtml(candidate);
            return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeUrl}</a>`;
        })
        .join('<br>');
}

function buildFarmersMarketRows(properties) {
    return [
        {
            label: 'Address',
            value: buildFarmersMarketAddress(properties),
        },
        {
            label: 'Hours',
            value: formatFarmersMarketValue('hours', properties.hours),
        },
        {
            label: 'Website',
            value: buildFarmersMarketWebsite(properties),
        },
        {
            label: 'County Market',
            value: formatFarmersMarketValue('isCounty', properties.isCounty),
        },
    ];
}

function buildFarmersMarketPopupContent(properties) {
    const name = isBlankValue(properties.name)
        ? 'Farmers Market'
        : escapeHtml(properties.name.trim());
    const propertyRows = buildFarmersMarketRows(properties)
        .map(function(row) {
            return `
                <div style="display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: 8px 12px; align-items: start; padding: 8px 0; border-bottom: 1px solid #ddd;">
                    <div style="font-weight: bold;">${escapeHtml(row.label)}</div>
                    <div style="min-width: 0; white-space: normal; overflow-wrap: anywhere; word-break: break-word;">
                        ${row.value}
                    </div>
                </div>
            `;
        })
        .join('');

    const rowsContent = propertyRows || `
        <div style="padding: 8px 0; color: #666;">No additional details available.</div>
    `;

    return `
        <div style="width: 360px; max-width: 70vw;">
            <div style="text-align: center; margin-bottom: 10px;">
                <h5 style="margin: 0;">${name}</h5>
            </div>
            <div style="max-height: 320px; overflow-y: auto; padding-right: 4px;">
                ${rowsContent}
            </div>
        </div>
    `;
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
        },
        drawFarmersMarketIcon: function(feature, latlng) {
            const MarketIcon = L.icon({
                iconUrl: '/assets/farmers_market_icon.png',
                iconSize: [25, 25]
            });
            const marker = L.marker(latlng, {icon: MarketIcon});
        
            if (feature.properties) {
                marker.bindPopup(
                    buildFarmersMarketPopupContent(feature.properties),
                    {
                        maxWidth: 420,
                        minWidth: 320,
                    }
                );
            }
        
            return marker;
        },
    }
});
