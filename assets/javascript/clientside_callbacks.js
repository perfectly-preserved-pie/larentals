window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        toggleVisibility: function(n_clicks) {
            if (n_clicks === undefined) {
                // PreventUpdate equivalent
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }

            var displayStyle = (n_clicks % 2 === 0) ? 'block' : 'none';
            var buttonText = (n_clicks % 2 === 0) ? "Hide" : "Show";
            
            return [{display: displayStyle}, buttonText];
        },
        toggleCollapse: function(n_clicks, is_open) {
            if (n_clicks === undefined) {
                return [false, "More Options"];
            }
            return [!is_open, is_open ? "More Options" : "Less Options"];
        },
        toggleVisibilityBasedOnSubtype: function(selected_subtype) {
            if (selected_subtype.includes('MH')) {
                return {'display': 'block'};
            } else {
                return {'display': 'none'};
            }
        },
        toggleHOAVisibility: function(selected_subtype) {
            if (selected_subtype.includes('MH') && selected_subtype.length === 1) {
                return {'display': 'none'};
            } else {
                return {
                    'display': 'block',
                    'marginBottom' : '10px',
                };
            }
        },
        filterAndCluster: function(sliderValue, rawData) {
            if (!rawData || !rawData.features) {
                // If missing or invalid, just return as-is or an empty FeatureCollection
                return rawData || {type: "FeatureCollection", features: []};
            }
            const [minPrice, maxPrice] = sliderValue;

            // Filter out features that don't meet the price criteria
            const filteredFeatures = rawData.features.filter(feature => {
                const price = feature.properties.list_price || 0;
                return price >= minPrice && price <= maxPrice;
            });

            // Return a new FeatureCollection with only those filtered features
            return {
                ...rawData,
                features: filteredFeatures
            };
        }
    }
});