// This is a JavaScript file to customize the Leaflet popup
// It should be used with dl.GeoJSON's `onEachFeature` option
// See https://github.com/perfectly-preserved-pie/larentals/issues/86#issuecomment-1585304809
window.dash_props = Object.assign({}, window.dash_props, {
    module: {
        on_each_feature: function(feature, layer) {
            //console.log("Feature properties:", feature.properties);
            if (!feature.properties) {
                console.log("Feature properties are missing.");
                return;
            }

            const data = feature.properties; // Use feature.properties directly
            const encodedData = encodeURIComponent(JSON.stringify(data)); // Encode the data as a JSON for the reportListing function
            const context = feature.properties.context; // Get the type of page (lease or buy) from the GeoJSON feature properties
            const selected_subtypes = data.subtype; // Get the selected subtype(s) from the GeoJSON feature properties

            /**
             * Converts placeholder values (e.g., "None", "null", empty strings) to null,
             * returning the trimmed string for any other input.
             *
             * @param {unknown} value Raw value supplied from the GeoJSON properties.
             * @returns {string|null} Normalized string or null when the value is missing/placeholder.
             */
            const normalizeNullableString = (value) => {
                if (value === null || value === undefined) {
                    return null;
                }
                const normalized = String(value).trim();
                if (!normalized || ["none", "null", "nan"].includes(normalized.toLowerCase())) {
                    return null;
                }
                return normalized;
            };

            // Strip a terminal '.0' without disturbing real decimals like 475.08
            const stripTrailingPointZero = (value) => {
                if (value === null || value === undefined) return value;
                const cleaned = String(value).replace(/\.0$/, "");
                if (typeof value === "number") {
                    const asNum = Number(cleaned);
                    return Number.isNaN(asNum) ? value : asNum;
                }
                return cleaned;
            };

            // Format lot size with commas, preserving up to two decimals and removing redundant trailing .0
            const formatLotSize = (value) => {
                if (value === null || value === undefined) return null;
                if (typeof value === "string") {
                    const normalized = value.replace(/,/g, "").trim();
                    if (!normalized || ["none", "null", "nan"].includes(normalized.toLowerCase())) return null;
                    const num = Number(normalized);
                    if (Number.isNaN(num)) return null;
                    const formatted = num % 1 === 0
                        ? num.toLocaleString("en-US")
                        : num.toLocaleString("en-US", { maximumFractionDigits: 2 });
                    return stripTrailingPointZero(formatted);
                }

                const num = Number(value);
                if (Number.isNaN(num)) return null;
                const formatted = num % 1 === 0
                    ? num.toLocaleString("en-US")
                    : num.toLocaleString("en-US", { maximumFractionDigits: 2 });
                return stripTrailingPointZero(formatted);
            };

            const listingUrl = normalizeNullableString(data.listing_url);
            const mlsPhoto = normalizeNullableString(data.mls_photo);
            const fullStreetAddress = stripTrailingPointZero(normalizeNullableString(data.full_street_address)) || "Unknown Address";
            const lotSizeDisplay = formatLotSize(data.lot_size);
            const mlsNumberDisplay = stripTrailingPointZero(data.mls_number);
            
            if (!context) {
                //console.log("Context is undefined.");
                return;
            }

            // Log the context object to debug
            //console.log('Context:', context);
            //console.log('Data:', data);

            // Function to handle MLS number hyperlink
            function getListingUrlBlock(address, listingUrlValue) {
                if (!listingUrlValue) {
                    return `
                        <div style="text-align: center;">
                            <h5>${address}</h5>
                        </div>
                    `;
                }
                return `
                    <div style="text-align: center;">
                        <h5><a href='${listingUrlValue}' referrerPolicy='noreferrer' target='_blank'>${address}</a></h5>
                    </div>
                `;
            }

            function buildImageRow(photoUrl, listingUrlValue) {
                if (!photoUrl) {
                    return '';
                }
                const imageTag = `<img src="${photoUrl}" alt="Property Image" style="width:100%;height:auto;">`;
                if (listingUrlValue) {
                    return `
                        <div style="position: relative;">
                            <a href="${listingUrlValue}" target="_blank" referrerPolicy="noreferrer">
                                ${imageTag}
                            </a>
                        </div>
                    `;
                }
                return `
                    <div style="position: relative;">
                        ${imageTag}
                    </div>
                `;
            }

            // Function to handle the Palisades fire alert
            function getPalisadesFireAlertBlock(data) {
                if (data.affected_by_palisades_fire === true || data.affected_by_palisades_fire === "True") {
                    return `
                        <div style="color: red; text-align: center;">
                            ⚠️ Affected by Palisades Fire. Please verify at <a href="https://recovery.lacounty.gov/palisades-fire/" target="_blank" style="color: red;">recovery.lacounty.gov</a>.
                        </div>
                    `;
                }
                return '';
            }

            // Function to handle the Eaton fire alert
            function getEatonFireAlertBlock(data) {
                if (data.affected_by_eaton_fire === true || data.affected_by_eaton_fire === "True") {
                    return `
                        <div style="color: red; text-align: center;">
                            ⚠️ Affected by Eaton Fire. Please verify at <a href="https://recovery.lacounty.gov/eaton-fire/" target="_blank" style="color: red;">recovery.lacounty.gov</a>.
                        </div>
                    `;
                }
                return '';
            }

            // Function to format date string
            function formatDate(dateString) {
                if (!dateString) return "Unknown";
                const date = new Date(dateString);
                return date.toISOString().split('T')[0];
            }

            // Conditionally format the listing URL as a hyperlink or plain text
            const listingUrlBlock = getListingUrlBlock(fullStreetAddress, listingUrl);

            // Conditionally include the property image row if the image URL is available
            const imageRow = buildImageRow(mlsPhoto, listingUrl);

            // Conditionally format the phone number as a tel: link or plain text
            const phoneNumberBlock = data.phone_number ? `
                <a href="tel:${data.phone_number}">${data.phone_number}</a>
            ` : 'Unknown';

            // Function to generate popup content for lease page
            function generateLeasePopupContent(data) {
                return `
                    <div>
                        ${getPalisadesFireAlertBlock(data)}
                        ${getEatonFireAlertBlock(data)}
                        ${imageRow}
                        ${listingUrlBlock}
                        <div class="property-card" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                            <!-- Listed Date -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listed Date</span>
                                <span class="value">${formatDate(data.listed_date)}</span>
                            </div>
                            <!-- Listing ID (MLS#) -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listing ID (MLS#)</span>
                                <span class="value">${mlsNumberDisplay}</span>
                            </div>
                            <!-- List Office Phone -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">List Office Phone</span>
                                <span class="value">${phoneNumberBlock}</span>
                            </div>
                            <!-- Rental Price -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Rental Price</span>
                                <span class="value">$${data.list_price.toLocaleString()}</span>
                            </div>
                            <!-- Security Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Security Deposit</span>
                                <span class="value">${data.security_deposit ? `$${data.security_deposit.toLocaleString()}` : "Unknown"}</span>
                            </div>
                            <!-- Pet Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Pet Deposit</span>
                                <span class="value">${data.pet_deposit ? `$${data.pet_deposit.toLocaleString()}` : "Unknown"}</span>
                            </div>
                            <!-- Key Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Key Deposit</span>
                                <span class="value">${data.key_deposit ? `$${data.key_deposit.toLocaleString()}` : "Unknown"}</span>
                            </div>
                            <!-- Other Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Other Deposit</span>
                                <span class="value">${data.other_deposit ? `$${data.other_deposit.toLocaleString()}` : "Unknown"}</span>
                            </div>
                            <!-- Square Feet -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Square Feet</span>
                                <span class="value">${data.sqft ? `${data.sqft.toLocaleString()} sq. ft` : "Unknown"}</span>
                            </div>
                            <!-- Price Per Square Foot -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Price Per Square Foot</span>
                                <span class="value">${data.ppsqft ? `$${data.ppsqft.toLocaleString()}` : "Unknown"}</span>
                            </div>
                            <!-- Bedrooms/Bathrooms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Bedrooms/Bathrooms</span>
                                <span class="value">${data.bedrooms}/${data.total_bathrooms}</span>
                            </div>
                            <!-- Parking Spaces -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Parking Spaces</span>
                                <span class="value">${data.parking_spaces || "Unknown"}</span>
                            </div>
                            <!-- Pets Allowed? -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Pets Allowed?</span>
                                <span class="value">${data.pet_policy || "Unknown"}</span>
                            </div>
                            <!-- Furnished? -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Furnished?</span>
                                <span class="value">${data.furnished || "Unknown"}</span>
                            </div>
                            <!-- Laundry Features -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Laundry Features</span>
                                <span class="value" style="white-space: normal; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word;">
                                    ${data.laundry || "Unknown"}
                                </span>
                            </div>
                            <!-- Senior Community -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Senior Community</span>
                                <span class="value">${data.senior_community || "Unknown"}</span>
                            </div>
                            <!-- Year Built -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Year Built</span>
                                <span class="value">${data.year_built || "Unknown"}</span>
                            </div>
                            <!-- Rental Terms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Rental Terms</span>
                                <span class="value">${data.terms || "Unknown"}</span>
                            </div>
                            <!-- Physical Sub Type -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Physical Sub Type</span>
                                <span class="value">${data.subtype || "Unknown"}</span>
                            </div>
                        </div>
                        <div style="text-align: center; margin-top: 10px;">
                            <a href="#" title="Report Listing" onclick='reportListing(decodeURIComponent("${encodedData}"))' style="text-decoration: none; color: red;">
                                <i class="fa-solid fa-flag" style="font-size:1.25em; vertical-align: middle;"></i>
                                <span style="vertical-align: middle; margin-left: 5px;">Report Listing</span>
                            </a>
                        </div>
                    </div>
                `;
            }

            // Function to generate popup content for buy page
            function generateBuyPopupContent(data) {
                // Include parking spaces if subtype is not 'SFR' or 'Single Family Residence'
                let parkingContent = '';
                if (!(data.subtype.includes('SFR') || data.subtype.includes('Single Family Residence'))) {
                    parkingContent = `
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Parking Spaces</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.garage_spaces || "Unknown"}</td>
                        </tr>
                    `;
                }

                // Conditional Senior Community
                let seniorCommunityContent = '';
                if (data.subtype.includes('MH')) {
                    seniorCommunityContent = `
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Senior Community</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.senior_community || "Unknown"}</td>
                        </tr>
                    `;
                }

                // Conditional Pets Allowed
                let petsAllowedContent = '';
                if (data.pets_allowed) {
                    petsAllowedContent = `
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Pets Allowed?</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.pets_allowed || "Unknown"}</td>
                        </tr>
                    `;
                }

                // Conditional Space Rent
                let spaceRentContent = '';
                if (data.subtype.includes('MH') || data.subtype.includes('Manufactured Home')) {
                    spaceRentContent = `
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Space Rent</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.space_rent || "Unknown"}</td>
                        </tr>
                    `;
                }

                return `
                    <div>
                    ${getPalisadesFireAlertBlock(data)}
                    ${getEatonFireAlertBlock(data)}
                    ${imageRow}
                    ${listingUrlBlock}
                    <table style="width:100%;border-collapse:collapse;">
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listed Date</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${formatDate(data.listed_date)}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listing ID (MLS#)</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${mlsNumberDisplay}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">List Office Phone</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${phoneNumberBlock || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">List Price</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">$${data.list_price.toLocaleString() || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">HOA Fee</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.hoa_fee ? `$${data.hoa_fee.toLocaleString()}` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">HOA Fee Frequency</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.hoa_fee_frequency || "Unknown"}</td>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Square Feet</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.sqft ? `${data.sqft.toLocaleString()}` : "Unknown"} sq. ft</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Price Per Square Foot</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.ppsqft ? `$${data.ppsqft.toLocaleString()}` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Lot Size</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${lotSizeDisplay ? `${lotSizeDisplay} sq. ft` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Bedrooms/Bathrooms</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.bedrooms}/${data.total_bathrooms}</td>
                        </tr>
                        ${parkingContent}
                        ${petsAllowedContent}
                        ${seniorCommunityContent}
                        ${spaceRentContent}
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Year Built</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.year_built || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Physical Sub Type</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.subtype || "Unknown"}</td>
                        </tr>
                    </table>
                    <div style="text-align:center; margin-top: 10px;">
                        <a href="#" title="Report Listing" onclick='reportListing(decodeURIComponent("${encodedData}"))' style="text-decoration: none; color: red;">
                            <i class="fa-solid fa-flag" style="font-size:1.25em; vertical-align: middle;"></i>
                            <span style="vertical-align: middle; margin-left: 5px;">Report Listing</span>
                        </a>
                    </div>
                </div>
                `;
            }

            // Determine which popup content to generate based on context
            let popupContent = '';
            if (context.pageType === 'lease') {
                popupContent = generateLeasePopupContent(data);
            } else if (context.pageType === 'buy') {
                popupContent = generateBuyPopupContent(data, selected_subtypes);
            }

            // Use Leaflet's map size to determine the popup size
            //const w = window.innerWidth;
            //const h = window.innerHeight;
            //const isMobile = L.Browser.mobile;

            // Compute maxWidth/maxHeight
            const isMobile = L.Browser.mobile || window.innerWidth < 768; // Use Leaflet's mobile detection or check window width
            const maxWidth  = isMobile ? 225 : 300;
            const maxHeight = isMobile ? 405 : 650;

            // Bind the popup to the layer with the generated content and size constraints
            layer.bindPopup(
                popupContent,
                {
                    maxWidth: maxWidth,
                    maxHeight: maxHeight,
                    //keepInView: true,
                    autoPanPadding: [10, 10],
                    closeButton: true,
                    //closeOnClick: false,
                    className: 'responsive-popup',
                }
            );
        }
    }
});