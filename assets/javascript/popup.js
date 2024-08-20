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

                // Ensure context has the necessary properties
                context = {
                    ...context,
                    mls_number: data.mls_number,
                    listing_url: data.listing_url
                };

                // Function to handle MLS number hyperlink
                function getListingUrlBlock(context) {
                    if (!context.mls_number) {
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
                            <td><a href='${context.listing_url}' referrerPolicy='noreferrer' target='_blank'>${context.mls_number}</a></td>
                        </tr>
                    `;
                }

                const listingUrlBlock = getListingUrlBlock(context);

                const popupContent = `
                    <div>
                        <img src="${data.image_url}" alt="Property Image" style="width:100%;height:auto;">
                        <h4>${data.address}</h4>
                        <table style="width:100%;border-collapse:collapse;">
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listed Date</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.listed_date}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Street Address</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.address}</td>
                            </tr>
                            ${listingUrlBlock}
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">List Office Phone</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.phone_number}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Rental Price</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">$${data.list_price.toLocaleString()}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Security Deposit</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">$${data.security_deposit.toLocaleString()}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Pet Deposit</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.pet_deposit}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Key Deposit</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.key_deposit}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Other Deposit</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.other_deposit}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Square Feet</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.sqft.toLocaleString()} sq. ft</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Price Per Square Foot</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">$${data.price_per_sqft.toLocaleString()}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Bedrooms/Bathrooms</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.bedrooms}/${data.bathrooms}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Garage Spaces</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.garage_spaces}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Pets Allowed?</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.pet_policy}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Furnished?</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.furnished}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Laundry Features</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.laundry}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Senior Community</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.SeniorCommunityYN}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Year Built</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.year_built}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Rental Terms</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.terms}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Physical Sub Type</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.subtype}</td>
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