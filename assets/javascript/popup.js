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
                        <h4>${data.address}</h4>
                        <p>MLS Number: ${data.mls_number}</p>
                        <p>List Price: ${data.list_price}</p>
                        <p>Bedrooms: ${data.bedrooms}</p>
                        <!-- <p>Bathrooms: ${data.bathrooms}</p> -->
                        <p>Square Feet: ${data.sqft}</p>
                        <p>Year Built: ${data.year_built}</p>
                        <p>Price per Sqft: ${data.price_per_sqft}</p>
                        <p>Listed Date: ${data.listed_date}</p>
                        <p>Subtype: ${data.subtype}</p>
                        <p>Pet Policy: ${data.pet_policy}</p>
                        <p>Terms: ${data.terms}</p>
                        <p>Garage Spaces: ${data.garage_spaces}</p>
                        <p>Furnished: ${data.furnished}</p>
                        <p>Security Deposit: ${data.security_deposit}</p>
                        <p>Pet Deposit: ${data.pet_deposit}</p>
                        <p>Key Deposit: ${data.key_deposit}</p>
                        <p>Other Deposit: ${data.other_deposit}</p>
                        <p>Laundry: ${data.laundry}</p>
                        <img src="${data.image_url}" alt="Property Image" style="width:100%;height:auto;">
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