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
                const data = feature.properties.data;
            
                // Log the context object to debug
                console.log('Context:', context);
            
                // Function to handle MLS number hyperlink
                function getListingUrlBlock(data) {
                    if (!data.mls_number) {
                        return `
                            <tr>
                                <td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id' target='_blank'>Listing ID (MLS#)</a></td>
                                <td>Not Available</td>
                            </tr>
                        `;
                    }
                    return `
                        <tr>
                            <td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id' target='_blank'>Listing ID (MLS#)</a></td>
                            <td><a href='${data.listing_url}' referrerPolicy='noreferrer' target='_blank'>${data.mls_number}</a></td>
                        </tr>
                    `;
                }
                
                // Function to format date string
                function formatDate(dateString) {
                    if (!dateString) return "Unknown";
                    const date = new Date(dateString);
                    return date.toISOString().split('T')[0];
                }
            
                const listingUrlBlock = getListingUrlBlock(data);
            
                const popupContent = `
                    <div>
                        <a href="${data.listing_url}" target="_blank" referrerPolicy="noreferrer">
                            <img src="${data.image_url}" alt="Property Image" style="width:100%;height:auto;">
                        </a>
                        <h4>${data.address}</h4>
                        <table style="width:100%;border-collapse:collapse;">
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listed Date</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${formatDate(data.listed_date) || "Unknown"}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Street Address</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.address}</td>
                            </tr>
                            ${listingUrlBlock}
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">List Office Phone</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.phone_number || "Unknown"}</td>
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
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Garage Spaces</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.garage_spaces || "Unknown"}</td>
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
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.laundry}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Senior Community</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.senior_community}</td>
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
            
                layer.bindPopup(popupContent, {
                    maxHeight: window.innerWidth < 768 ? 375 : 650,
                    maxWidth: window.innerWidth < 768 ? 175 : 300,
                });
            }
        }
    }
});