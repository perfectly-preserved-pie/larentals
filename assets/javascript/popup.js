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
            const context = feature.properties.context; // Get the type of page (lease or buy) from the GeoJSON feature properties
            const selected_subtypes = data.subtype; // Get the selected subtype(s) from the GeoJSON feature properties

            if (!context) {
                //console.log("Context is undefined.");
                return;
            }

            // Log the context object to debug
            //console.log('Context:', context);
            //console.log('Data:', data);

            // Function to handle MLS number hyperlink
            function getListingUrlBlock(data) {
                if (!data.listing_url) {
                    return `
                        <div style="text-align: center;">
                            <h5>${data.full_street_address}</h5>
                        </div>
                    `;
                }
                return `
                    <div style="text-align: center;">
                        <h5><a href='${data.listing_url}' referrerPolicy='noreferrer' target='_blank'>${data.full_street_address}</a></h5>
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
            const listingUrlBlock = getListingUrlBlock(data);

            // Conditionally include the property image row if the image URL is available
            const imageRow = data.mls_photo ? `
            <a href="${data.listing_url}" target="_blank" referrerPolicy="noreferrer">
                <img src="${data.mls_photo}" alt="Property Image" style="width:100%;height:auto;">
            </a>
            ` : '';

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
                    <table style="width:100%;border-collapse:collapse;">
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listed Date</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${formatDate(data.listed_date)}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listing ID (MLS#)</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.mls_number}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">List Office Phone</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${phoneNumberBlock}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Rental Price</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">$${data.list_price.toLocaleString()}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Security Deposit</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.security_deposit ? `$${data.security_deposit.toLocaleString()}` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Pet Deposit</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.pet_deposit ? `$${data.pet_deposit.toLocaleString()}` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Key Deposit</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.key_deposit ? `$${data.key_deposit.toLocaleString()}` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Other Deposit</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.other_deposit ? `$${data.other_deposit.toLocaleString()}` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Square Feet</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.sqft ? `${data.sqft.toLocaleString()}` : "Unknown"} sq. ft</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Price Per Square Foot</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.ppsqft ? `$${data.ppsqft.toLocaleString()}` : "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Bedrooms/Bathrooms</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.bedrooms}/${data.total_bathrooms}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Parking Spaces</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.parking_spaces || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Pets Allowed?</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.pet_policy || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Furnished?</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.furnished || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Laundry Features</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.laundry || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Senior Community</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.senior_community || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Year Built</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.year_built || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Rental Terms</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.terms || "Unknown"}</td>
                        </tr>
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Physical Sub Type</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.subtype || "Unknown"}</td>
                        </tr>
                    </table>
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
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.mls_number}</td>
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
                            <td style="padding:8px;border-bottom:1px solid #ddd;">${data.lot_size ? `${data.lot_size.toLocaleString()} sq. ft` : "Unknown"}</td>
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

            // Bind the popup to the layer and set the max height and width based on the screen size
            layer.bindPopup(popupContent, {
                maxHeight: window.innerWidth < 768 ? 375 : 650,
                maxWidth: window.innerWidth < 768 ? 175 : 300,
            });
        }
    }
});