/**
 * @typedef {Record<string, unknown>} LayerProperties
 */

/**
 * @typedef {{ label: string, value: string }} PopupRow
 */

/**
 * @typedef {{ properties?: LayerProperties }} LayerFeature
 */

/**
 * Convert a military-style time value into a 12-hour display string.
 *
 * @param {unknown} time Raw time value, typically in `HHMM` form.
 * @returns {string} Formatted 12-hour time string.
 */
function militaryToStandard(time) {
    // Convert the time to a string if it's not already
    time = String(time);

    // Pad the time with zeros if it's less than 4 digits
    while (time.length < 4) {
        time = '0' + time;
    }

    var hours = parseInt(time.substring(0, 2), 10);
    var minutes = parseInt(time.substring(2, 4), 10);
    var suffix = hours >= 12 ? 'PM' : 'AM';

    // Convert to 12-hour time
    hours = ((hours + 11) % 12) + 1;

    // Pad the minutes with a leading zero if they're less than 10
    minutes = minutes < 10 ? '0' + minutes : minutes;

    return hours + ':' + minutes + ' ' + suffix;
}

/**
 * Check whether a popup value should be treated as blank.
 *
 * @param {unknown} value Raw property value.
 * @returns {boolean} `true` when the value is empty or null-like.
 */
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

/**
 * Escape text for safe HTML interpolation inside popup content.
 *
 * @param {unknown} value Raw text value to escape.
 * @returns {string} HTML-safe string.
 */
function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Format a popup date value for display.
 *
 * @param {unknown} value Raw date-like value from a feature property.
 * @returns {string} Escaped date string, or `N/A` when the value is blank.
 */
function formatPopupDate(value) {
    if (isBlankValue(value)) {
        return 'N/A';
    }

    const valueAsString = String(value).trim();
    if (valueAsString.includes('T')) {
        return escapeHtml(valueAsString.split('T')[0]);
    }

    return escapeHtml(valueAsString);
}

/**
 * Convert a raw property key into a human-friendly label.
 *
 * @param {string} key Raw property key.
 * @returns {string} Display label for popup rows.
 */
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

/**
 * Format a farmers market property value for popup display.
 *
 * @param {string} key Property key being rendered.
 * @param {unknown} value Raw property value.
 * @returns {string} Escaped HTML string for the property value.
 */
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

/**
 * Join address fragments while filtering blank values.
 *
 * @param {unknown[]} parts Address fragments in display order.
 * @returns {string} Comma-separated address string.
 */
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

/**
 * Build the formatted address line for a farmers market popup.
 *
 * @param {LayerProperties} properties Feature properties for the farmers market.
 * @returns {string} Escaped address string, or `N/A` when unavailable.
 */
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

/**
 * Build the website block for a farmers market popup.
 *
 * @param {LayerProperties} properties Feature properties for the farmers market.
 * @returns {string} HTML link block, or `N/A` when no site is available.
 */
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

/**
 * Build the ordered rows rendered in a farmers market popup.
 *
 * @param {LayerProperties} properties Feature properties for the farmers market.
 * @returns {PopupRow[]} Popup rows for the feature.
 */
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

/**
 * Build the popup title for a farmers market feature.
 *
 * @param {LayerProperties} properties Feature properties for the farmers market.
 * @returns {string} Escaped display title.
 */
function buildFarmersMarketTitle(properties) {
    if (isBlankValue(properties.name)) {
        return 'Farmers Market';
    }

    const rawName = String(properties.name).trim();
    const expandedName = rawName.replace(/\bCFM\b/g, 'Certified Farmers Market').trim();

    if (/farmers market/i.test(expandedName)) {
        return escapeHtml(expandedName);
    }

    return escapeHtml(`${expandedName} Farmers Market`);
}

/**
 * Build the complete farmers market popup markup.
 *
 * @param {LayerProperties} properties Feature properties for the farmers market.
 * @returns {string} HTML string bound to the Leaflet popup.
 */
function buildFarmersMarketPopupContent(properties) {
    const marketName = buildFarmersMarketTitle(properties);
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
                <h5 style="margin: 0;">${marketName}</h5>
            </div>
            <div style="max-height: 320px; overflow-y: auto; padding-right: 4px;">
                ${rowsContent}
            </div>
        </div>
    `;
}

/**
 * Normalize text into title case when the source is all upper or all lower case.
 *
 * @param {unknown} value Raw text value to normalize.
 * @returns {string|null} Title-cased string, or `null` when blank.
 */
function toDisplayTitleCase(value) {
    if (isBlankValue(value)) {
        return null;
    }

    const normalized = String(value).trim().replace(/\s+/g, ' ');
    const needsNormalization = normalized === normalized.toUpperCase() || normalized === normalized.toLowerCase();
    if (!needsNormalization) {
        return normalized;
    }

    return normalized
        .toLowerCase()
        .replace(/\b([a-z])([a-z']*)/g, function(match, firstLetter, restOfWord) {
            return firstLetter.toUpperCase() + restOfWord;
        });
}

/**
 * Build the popup title for a supermarket feature.
 *
 * @param {LayerProperties} properties Feature properties for the supermarket.
 * @returns {string} Escaped title for the popup header.
 */
function buildSupermarketTitle(properties) {
    const dbaName = isBlankValue(properties.dba_name)
        ? null
        : String(properties.dba_name).trim();
    const businessName = isBlankValue(properties.business_name)
        ? null
        : String(properties.business_name).trim();
    const title = toDisplayTitleCase(dbaName || businessName || 'Supermarket / Grocery Store');

    return escapeHtml(title);
}

/**
 * Build the formatted address string for a supermarket popup.
 *
 * @param {LayerProperties} properties Feature properties for the supermarket.
 * @returns {string} Escaped address string, or `N/A` when unavailable.
 */
function buildSupermarketAddress(properties) {
    if (!isBlankValue(properties.full_address)) {
        return escapeHtml(toDisplayTitleCase(properties.full_address));
    }

    const address = joinAddressParts([
        properties.street_address,
        properties.city,
        properties.zip_code,
    ]);
    return address ? escapeHtml(toDisplayTitleCase(address)) : 'N/A';
}

/**
 * Build the category row for a supermarket popup.
 *
 * @param {LayerProperties} properties Feature properties for the supermarket.
 * @returns {PopupRow|null} Category row, or `null` when no category metadata exists.
 */
function buildSupermarketCategoryRow(properties) {
    if (!isBlankValue(properties.naics)) {
        const description = isBlankValue(properties.primary_naics_description)
            ? ''
            : ` - ${escapeHtml(String(properties.primary_naics_description).trim())}`;
        return {
            label: 'NAICS',
            value: `${escapeHtml(String(properties.naics).trim())}${description}`,
        };
    }

    if (!isBlankValue(properties.business_type)) {
        return {
            label: 'Business Type',
            value: escapeHtml(String(properties.business_type).trim()),
        };
    }

    return null;
}

/**
 * Build the complete supermarket popup markup.
 *
 * @param {LayerProperties} properties Feature properties for the supermarket.
 * @returns {string} HTML string bound to the Leaflet popup.
 */
function buildSupermarketPopupContent(properties) {
    const rows = [
        {
            label: 'Address',
            value: buildSupermarketAddress(properties),
        },
        buildSupermarketCategoryRow(properties),
        isBlankValue(properties.location_start_date) ? null : {
            label: 'Opened',
            value: escapeHtml(String(properties.location_start_date).trim()),
        },
    ].filter(Boolean);

    const propertyRows = rows
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

    return `
        <div style="width: 360px; max-width: 70vw;">
            <div style="text-align: center; margin-bottom: 10px;">
                <h5 style="margin: 0;">${buildSupermarketTitle(properties)}</h5>
            </div>
            <div style="max-height: 320px; overflow-y: auto; padding-right: 4px;">
                ${propertyRows}
            </div>
        </div>
    `;
}

/**
 * Build the address row value for a breakfast burrito popup.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {string} Escaped address or linked map destination.
 */
function buildBreakfastBurritoAddress(properties) {
    if (isBlankValue(properties.address)) {
        if (isBlankValue(properties.maps_url)) {
            return 'N/A';
        }

        const safeUrl = escapeHtml(String(properties.maps_url).trim());
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">Open in Google Maps</a>`;
    }

    const safeAddress = escapeHtml(String(properties.address).trim());
    if (isBlankValue(properties.maps_url)) {
        return safeAddress;
    }

    const safeUrl = escapeHtml(String(properties.maps_url).trim());
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeAddress}</a>`;
}

/**
 * Build the rating row value for a breakfast burrito popup.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {string} Rating display string, or `N/A`.
 */
function buildBreakfastBurritoRating(properties) {
    if (isBlankValue(properties.rating)) {
        return 'N/A';
    }

    return `${escapeHtml(String(properties.rating).trim())} / 10`;
}

/**
 * Build the photo row value for a breakfast burrito popup.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {string} HTML link to the photo, or `N/A`.
 */
function buildBreakfastBurritoPhoto(properties) {
    if (isBlankValue(properties.picture_url)) {
        return 'N/A';
    }

    const safeUrl = escapeHtml(String(properties.picture_url).trim());
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">View photo</a>`;
}

/**
 * Build the review/source row value for a breakfast burrito popup.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {string} HTML link to the best available review/source page, or `N/A`.
 */
function buildBreakfastBurritoOriginalReview(properties) {
    if (!isBlankValue(properties.review_url)) {
        const safeUrl = escapeHtml(String(properties.review_url).trim());
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">Read on LABreakfastBurrito</a>`;
    }

    if (!isBlankValue(properties.source_url)) {
        const safeUrl = escapeHtml(String(properties.source_url).trim());
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">Browse LABreakfastBurrito</a>`;
    }

    if (!isBlankValue(properties.source_sheet_url)) {
        const safeUrl = escapeHtml(String(properties.source_sheet_url).trim());
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">Open rankings sheet</a>`;
    }

    return 'N/A';
}

/**
 * Build the attribution source links for a breakfast burrito popup.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {string} Joined attribution links, or `N/A`.
 */
function buildBreakfastBurritoSource(properties) {
    const links = [];

    if (!isBlankValue(properties.review_url)) {
        const safeUrl = escapeHtml(String(properties.review_url).trim());
        links.push(`<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">Original review</a>`);
    }

    if (!isBlankValue(properties.source_url)) {
        const safeUrl = escapeHtml(String(properties.source_url).trim());
        links.push(`<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">LABreakfastBurrito</a>`);
    }

    if (!isBlankValue(properties.source_sheet_url)) {
        const safeUrl = escapeHtml(String(properties.source_sheet_url).trim());
        links.push(`<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">Rankings sheet</a>`);
    }

    return links.length > 0 ? links.join(' | ') : 'N/A';
}

/**
 * Build the attribution banner displayed above breakfast burrito popup rows.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {string} HTML banner, or an empty string when no attribution links exist.
 */
function buildBreakfastBurritoAttribution(properties) {
    const sourceLinks = buildBreakfastBurritoSource(properties);
    if (sourceLinks === 'N/A') {
        return '';
    }

    return `
        <div style="margin-bottom: 12px; padding: 10px 12px; border-radius: 10px; background: #fff3d6; border: 1px solid #e5c98a; color: #5b3312; line-height: 1.4;">
            <div style="font-weight: bold; margin-bottom: 4px;">Source Attribution</div>
            <div>
                Breakfast burrito rankings and review content are sourced from LABreakfastBurrito.
            </div>
            <div style="margin-top: 4px;">
                ${sourceLinks}
            </div>
        </div>
    `;
}

/**
 * Build the detail rows rendered inside a breakfast burrito popup.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {PopupRow[]} Popup rows for the feature.
 */
function buildBreakfastBurritoRows(properties) {
    return [
        {
            label: 'Status',
            value: isBlankValue(properties.review_status)
                ? 'N/A'
                : escapeHtml(String(properties.review_status).trim()),
        },
        {
            label: 'Rating',
            value: buildBreakfastBurritoRating(properties),
        },
        {
            label: 'Neighborhood',
            value: isBlankValue(properties.neighborhood)
                ? 'N/A'
                : escapeHtml(String(properties.neighborhood).trim()),
        },
        {
            label: 'Price',
            value: isBlankValue(properties.price)
                ? 'N/A'
                : escapeHtml(String(properties.price).trim()),
        },
        {
            label: 'Size',
            value: isBlankValue(properties.size)
                ? 'N/A'
                : escapeHtml(String(properties.size).trim()),
        },
        {
            label: 'Value',
            value: isBlankValue(properties.value_rating)
                ? 'N/A'
                : escapeHtml(String(properties.value_rating).trim()),
        },
        {
            label: 'Address',
            value: buildBreakfastBurritoAddress(properties),
        },
        {
            label: "What's Inside",
            value: isBlankValue(properties.whats_inside)
                ? 'N/A'
                : escapeHtml(String(properties.whats_inside).trim()),
        },
        {
            label: 'Photo',
            value: buildBreakfastBurritoPhoto(properties),
        },
        {
            label: isBlankValue(properties.review_url) ? 'Source' : 'Original Review',
            value: buildBreakfastBurritoOriginalReview(properties),
        },
    ];
}

/**
 * Build the complete breakfast burrito popup markup.
 *
 * @param {LayerProperties} properties Feature properties for the breakfast burrito entry.
 * @returns {string} HTML string bound to the Leaflet popup.
 */
function buildBreakfastBurritoPopupContent(properties) {
    const title = isBlankValue(properties.name)
        ? 'Breakfast Burrito'
        : escapeHtml(String(properties.name).trim());
    const propertyRows = buildBreakfastBurritoRows(properties)
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
    return `
        <div style="width: 380px; max-width: 72vw;">
            <div style="text-align: center; margin-bottom: 10px;">
                <h5 style="margin: 0;">${title}</h5>
            </div>
            <div style="max-height: 340px; overflow-y: auto; padding-right: 4px;">
                ${buildBreakfastBurritoAttribution(properties)}
                ${propertyRows}
            </div>
        </div>
    `;
}

const BREAKFAST_BURRITO_ICON_URL = 'https://api.iconify.design/twemoji/burrito.svg?width=18&height=18';

window.myNamespace = Object.assign({}, window.myNamespace, {
    mySubNamespace: {
        /**
         * Create the oil/gas well marker and bind its popup content.
         *
         * @param {LayerFeature} feature GeoJSON feature for the oil/gas well.
         * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
         * @returns {L.Marker} Marker configured for the feature.
         */
        drawOilIcon: function(feature, latlng) {
            const OilIcon = L.icon({
                iconUrl: '/assets/oil_derrick_icon.png',
                iconSize: [20, 20]  // Adjust the size as needed
            });
            var marker = L.marker(latlng, {icon: OilIcon});
            
            // Check if the required properties exist and create the popup content
            if (feature.properties) {
                const statusLabels = {
                    A: 'Active',
                    B: 'Buried',
                    I: 'Idle',
                    N: 'New',
                    P: 'Plugged',
                    U: 'Unknown',
                };
                const statusColors = {
                    A: 'red',
                    B: '#6c757d',
                    I: '#DAA520',
                    N: '#0d6efd',
                    P: 'green',
                    U: 'black',
                };
                const statusCode = isBlankValue(feature.properties.WellStatus)
                    ? null
                    : String(feature.properties.WellStatus).trim();
                const statusLabel = statusCode && statusLabels[statusCode]
                    ? `${statusLabels[statusCode]} (${statusCode})`
                    : (statusCode || 'N/A');
                const statusColor = statusCode && statusColors[statusCode]
                    ? statusColors[statusCode]
                    : 'black';
                const wellNumber = isBlankValue(feature.properties.WellNumber)
                    ? null
                    : escapeHtml(String(feature.properties.WellNumber).trim());
                const fieldName = isBlankValue(feature.properties.FieldName)
                    ? null
                    : escapeHtml(String(feature.properties.FieldName).trim());
                const apiNumber = isBlankValue(feature.properties.APINumber)
                    ? null
                    : escapeHtml(String(feature.properties.APINumber).trim());
                const popupTitle = fieldName && wellNumber
                    ? `${fieldName} • Well ${wellNumber}`
                    : wellNumber
                    ? `Oil/Gas Well Number ${wellNumber}`
                    : `Oil/Gas Well API ${apiNumber || 'Unknown'}`;
                var popupContent = `<h4>${popupTitle}</h4>`;
                popupContent += 'API Number: ' + (feature.properties.APINumber || feature.properties.API || 'N/A') + '<br>';
                popupContent += 'Operator: ' + (feature.properties.OperatorNa || 'N/A') + '<br>';
                popupContent += 'Field Name: ' + (feature.properties.FieldName || 'N/A') + '<br>';
                popupContent += 'County: ' + (feature.properties.CountyName || 'N/A') + '<br>';
                popupContent += 'Start Date: ' + formatPopupDate(feature.properties.SPUDDate) + '<br>';
                popupContent += 'Completion Date: ' + formatPopupDate(feature.properties.Completion) + '<br>';
                if (!isBlankValue(feature.properties.AbandonedD)) {
                    popupContent += 'Abandoned Date: ' + formatPopupDate(feature.properties.AbandonedD) + '<br>';
                }
                popupContent += 'Latest Update: ' + formatPopupDate(feature.properties.LatestUpdate) + '<br>';
                popupContent += 'Well Status: <span style="color:' + statusColor + ';">' + statusLabel + '</span><br>';
                
                marker.bindPopup(popupContent);
            }

            return marker;
        },
        /**
         * Create the crime marker and bind its popup content.
         *
         * @param {LayerFeature} feature GeoJSON feature for the crime record.
         * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
         * @returns {L.Marker} Marker configured for the feature.
         */
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
        /**
         * Create the breakfast burrito marker and bind its popup content.
         *
         * @param {LayerFeature} feature GeoJSON feature for the breakfast burrito location.
         * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
         * @returns {L.Marker} Marker configured for the feature.
         */
        drawBreakfastBurritoIcon: function(feature, latlng) {
            const BreakfastBurritoIcon = L.divIcon({
                className: 'breakfast-burrito-div-icon',
                html: `
                    <div style="width: 28px; height: 22px; border-radius: 999px; background: linear-gradient(135deg, #f4c978, #d87f2d); display: flex; align-items: center; justify-content: center; border: 2px solid #ffffff; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);">
                        <img
                            src="${BREAKFAST_BURRITO_ICON_URL}"
                            alt=""
                            width="18"
                            height="18"
                            style="display: block;"
                        >
                    </div>
                `,
                iconSize: [28, 22],
                iconAnchor: [14, 11],
                popupAnchor: [0, -12],
            });
            const marker = L.marker(latlng, {icon: BreakfastBurritoIcon});

            if (feature.properties) {
                marker.bindPopup(
                    buildBreakfastBurritoPopupContent(feature.properties),
                    {
                        maxWidth: 440,
                        minWidth: 320,
                    }
                );
            }

            return marker;
        },
        /**
         * Create the farmers market marker and bind its popup content.
         *
         * @param {LayerFeature} feature GeoJSON feature for the farmers market.
         * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
         * @returns {L.Marker} Marker configured for the feature.
         */
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
        /**
         * Create the supermarket marker and bind its popup content.
         *
         * @param {LayerFeature} feature GeoJSON feature for the supermarket.
         * @param {unknown} latlng Leaflet lat/lng argument supplied by the layer renderer.
         * @returns {L.Marker} Marker configured for the feature.
         */
        drawSupermarketIcon: function(feature, latlng) {
            const SupermarketIcon = L.divIcon({
                className: 'supermarket-div-icon',
                html: `
                    <div style="width: 22px; height: 22px; border-radius: 50%; background: #2f7d32; display: flex; align-items: center; justify-content: center; border: 2px solid #ffffff; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);">
                        <span style="color: #ffffff; font-size: 12px; line-height: 1;">&#128722;</span>
                    </div>
                `,
                iconSize: [22, 22],
                iconAnchor: [11, 11],
                popupAnchor: [0, -12],
            });
            const marker = L.marker(latlng, {icon: SupermarketIcon});

            if (feature.properties) {
                marker.bindPopup(
                    buildSupermarketPopupContent(feature.properties),
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
