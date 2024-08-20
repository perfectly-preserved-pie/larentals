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
                const popupContent = `
                    <div>
                        <img src="${data.image_url}" alt="Property Image" style="width:100%;height:auto;">
                        <h4>${data.address}</h4>
                        <table style="width:100%;border-collapse:collapse;">
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">MLS Number</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.mls_number}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">List Price</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.list_price}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Bedrooms</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.bedrooms}</td>
                            </tr>
                            <!-- <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Bathrooms</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.bathrooms}</td>
                            </tr> -->
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Square Feet</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.sqft}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Year Built</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.year_built}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Price per Sqft</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.price_per_sqft}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Listed Date</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.listed_date}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Subtype</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.subtype}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Pet Policy</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.pet_policy}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Terms</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.terms}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Garage Spaces</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.garage_spaces}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Furnished</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.furnished}</td>
                            </tr>
                            <tr>
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Security Deposit</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.security_deposit}</td>
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
                                <th style="text-align:left;padding:8px;border-bottom:1px solid #ddd;">Laundry</th>
                                <td style="padding:8px;border-bottom:1px solid #ddd;">${data.laundry}</td>
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