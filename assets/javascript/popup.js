// This is a JavaScript file to customize the Leaflet popup
// It should be used with dl.GeoJSON's `onEachFeature` option
// See https://github.com/perfectly-preserved-pie/larentals/issues/86#issuecomment-1585304809
window.dash_props = Object.assign({}, window.dash_props, {
    module: {
        on_each_feature: function(feature, layer, context) {
            if (!feature.properties) {
                return;
            }
            if (feature.properties.data) {
                const data = feature.properties.data; // Get the dataframe rows from the GeoJSON feature properties
                const context = feature.properties.context; // Get the type of page (lease or buy) from the GeoJSON feature properties
                const selected_subtypes = data.subtype; // Get the selected subtype(s) from the GeoJSON feature properties
            
                // Log the context object to debug
                //console.log('Context:', context);
                //console.log('Data:', data);
            
                // Function to handle MLS number hyperlink
                function getListingUrlBlock(data) {
                    if (!data.listing_url) {
                        return `
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listing ID (MLS#)</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">Not Available</td>
                            </tr>
                        `;
                    }
                    return `
                        <tr>
                            <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listing ID (MLS#)</th>
                            <td style="padding:8px;border-bottom:1px solid #ddd;">
                                <a href='${data.listing_url}' referrerPolicy='noreferrer' target='_blank'>${data.mls_number}</a>
                            </td>
                        </tr>
                    `;
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
                const imageRow = data.image_url ? `
                <a href="${data.listing_url}" target="_blank" referrerPolicy="noreferrer">
                    <img src="${data.image_url}" alt="Property Image" style="width:100%;height:auto;">
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
                        ${imageRow}
                        <div style="text-align: center;">
                            <h5>${data.address}</h5>
                        </div>
                        <table style="width:100%;border-collapse:collapse;">
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listed Date</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${formatDate(data.listed_date)}</td>
                            </tr>
                            ${listingUrlBlock}
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
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.bedrooms}/${data.bathrooms}</td>
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
                function generateBuyPopupContent(data, selected_subtypes) {
                    // Conditionally include the park name row if the property subtype is MH or has MH in the selected subtypes
                    let parkNameBlock = '';
                    if (selected_subtypes.includes('MH')) {
                        parkNameBlock = `
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Park Name</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.park_name || "Unknown"}</td>
                            </tr>
                        `;
                    }

                    // Conditionally include the pet policy row if the property subtype is MH or has MH in the selected subtypes
                    let petsAllowedBlock = '';
                    if (selected_subtypes.includes('MH')) {
                        petsAllowedBlock = `
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Pets Allowed?</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.pets_allowed || "Unknown"}</td>
                            </tr>
                        `;
                    }

                    // Condtionally include the Senior Community row if the property subtype is MH or has MH in the selected subtypes
                    let seniorCommunityBlock = '';
                    if (selected_subtypes.includes('MH')) {
                        seniorCommunityBlock = `
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Senior Community</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.senior_community || "Unknown"}</td>
                            </tr>
                        `;
                    }

                    // Conditionally include the space rent row if the property subtype is MH or has MH in the selected subtypes
                    let spaceRentBlock = '';
                    if (selected_subtypes.includes('MH')) {
                        spaceRentBlock = `
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Space Rent</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.space_rent ? `$${data.space_rent.toLocaleString()}` : "Unknown"}</td>
                            </tr>
                        `;
                    }

                    // Conditionally include the HOA Fee row if the property subtype is not MH or has MH in the selected subtypes
                    let hoaFeeBlock = '';
                    if (!selected_subtypes.includes('MH')) {
                        hoaFeeBlock = `
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">HOA Fee</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.hoa_fee ? `$${data.hoa_fee.toLocaleString()}` : "Unknown"}</td>
                            </tr>
                        `;
                    }

                    // Conditionally include the HOA Fee Frequency row if the property subtype is not MH or has MH in the selected subtypes
                    let hoaFeeFrequencyBlock = '';
                    if (!selected_subtypes.includes('MH')) {
                        hoaFeeFrequencyBlock = `
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">HOA Fee Frequency</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.hoa_fee_frequency || "Unknown"}</td>
                            </tr>
                        `;
                    }

                    return `
                        <div>
                            ${imageRow}
                            <div style="text-align: center;">
                                <h5>${data.address}</h5>
                            </div>
                            <table style="width:100%;border-collapse:collapse;">
                                <tr>
                                    <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listed Date</th>
                                    <td style="padding:8px;border-bottom:1px solid #ddd;">${formatDate(data.listed_date)}</td>
                                </tr>
                                ${listingUrlBlock}
                                ${parkNameBlock}
                                <tr>
                                    <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">List Price</th>
                                    <td style="padding:8px;border-bottom:1px solid #ddd;">$${data.list_price.toLocaleString()}</td>
                                </tr>
                                ${hoaFeeBlock}
                                ${hoaFeeFrequencyBlock}
                                <tr>
                                    <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Square Feet</th>
                                    <td style="padding:8px;border-bottom:1px solid #ddd;">${data.sqft ? `${data.sqft.toLocaleString()}` : "Unknown"} sq. ft</td>
                                </tr>
                                <tr>
                                    <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Price Per Square Foot</th>
                                    <td style="padding:8px;border-bottom:1px solid #ddd;">${data.ppsqft ? `$${data.ppsqft.toLocaleString()}` : "Unknown"}</td>
                                </tr>
                                ${spaceRentBlock}
                                <tr>
                                    <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Bedrooms/Bathrooms</th>
                                    <td style="padding:8px;border-bottom:1px solid #ddd;">${data.bedrooms_bathrooms}</td>
                                </tr>
                                <tr>
                                    <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Year Built</th>
                                    <td style="padding:8px;border-bottom:1px solid #ddd;">${data.year_built || "Unknown"}</td>
                                </tr>
                                ${petsAllowedBlock}
                                ${seniorCommunityBlock}
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

                layer.bindPopup(popupContent, {
                    maxHeight: window.innerWidth < 768 ? 375 : 650,
                    maxWidth: window.innerWidth < 768 ? 175 : 300,
                });
            }
        }
    }
});