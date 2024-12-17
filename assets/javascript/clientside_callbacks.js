// assets/javascript/clientside_callbacks.js

window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        // Existing functions
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
        // Filter functions
        // Filter for square footage
        sqftFilter: function(feature, filters) {
            const sqft = feature.properties.data?.sqft;
            if (sqft === null || sqft === undefined) {
                return filters.include_missing_sqft;
            }
            return sqft >= filters.sqft_slider[0] && sqft <= filters.sqft_slider[1];
        },

        // Filter for year built
        yrBuiltFilter: function(feature, filters) {
            const yearBuilt = feature.properties.data?.year_built;
            if (yearBuilt === null || yearBuilt === undefined) {
                return filters.include_missing_yr_built;
            }
            return yearBuilt >= filters.year_built_slider[0] && yearBuilt <= filters.year_built_slider[1];
        },

        // Filter for garage spaces
        garageFilter: function(feature, filters) {
            const parkingSpaces = feature.properties.data?.parking_spaces;
            if (parkingSpaces === null || parkingSpaces === undefined) {
                return filters.include_missing_garage_spaces;
            }
            return parkingSpaces >= filters.garage_spaces_slider[0] && parkingSpaces <= filters.garage_spaces_slider[1];
        },

        // Filter for price per square foot
        ppsqftFilter: function(feature, filters) {
            const ppsqft = feature.properties.data?.ppsqft;
            if (ppsqft === null || ppsqft === undefined) {
                return filters.include_missing_ppsqft;
            }
            return ppsqft >= filters.ppsqft_slider[0] && ppsqft <= filters.ppsqft_slider[1];
        },

        // Filter for pet policy
        petsFilter: function(feature, filters) {
            const petPolicy = feature.properties.data?.pet_policy || 'Unknown';
            if (filters.pets_choice === 'Both') {
                return true;
            } else if (filters.pets_choice === 'Yes') {
                return !['No', 'No, Size Limit'].includes(petPolicy);
            } else if (filters.pets_choice === 'No') {
                return ['No', 'No, Size Limit'].includes(petPolicy);
            }
            return true;
        },

        // Filter for furnished status
        furnishedFilter: function(feature, filters) {
            const furnished = feature.properties.data?.furnished || 'Unknown';
            if (!filters.furnished_choice || filters.furnished_choice.length === 0) {
                return true; // If no choices selected, include all
            }
            if (filters.furnished_choice.includes('Unknown') && (furnished === null || furnished === undefined)) {
                return true;
            }
            return filters.furnished_choice.includes(furnished);
        },

        // Filter for security deposit
        securityDepositFilter: function(feature, filters) {
            const securityDeposit = feature.properties.data?.security_deposit;
            if (securityDeposit === null || securityDeposit === undefined) {
                return filters.include_missing_security_deposit;
            }
            return securityDeposit >= filters.security_deposit_slider[0] && securityDeposit <= filters.security_deposit_slider[1];
        },

        // Filter for pet deposit
        petDepositFilter: function(feature, filters) {
            const petDeposit = feature.properties.data?.pet_deposit;
            if (petDeposit === null || petDeposit === undefined) {
                return filters.include_missing_pet_deposit;
            }
            return petDeposit >= filters.pet_deposit_slider[0] && petDeposit <= filters.pet_deposit_slider[1];
        },

        // Filter for key deposit
        keyDepositFilter: function(feature, filters) {
            const keyDeposit = feature.properties.data?.key_deposit;
            if (keyDeposit === null || keyDeposit === undefined) {
                return filters.include_missing_key_deposit;
            }
            return keyDeposit >= filters.key_deposit_slider[0] && keyDeposit <= filters.key_deposit_slider[1];
        },

        // Filter for other deposit
        otherDepositFilter: function(feature, filters) {
            const otherDeposit = feature.properties.data?.other_deposit;
            if (otherDeposit === null || otherDeposit === undefined) {
                return filters.include_missing_other_deposit;
            }
            return otherDeposit >= filters.other_deposit_slider[0] && otherDeposit <= filters.other_deposit_slider[1];
        },

        // Filter for listed date
        listedDateFilter: function(feature, filters) {
            const listedDateStr = feature.properties.data?.listed_date;
            if (!listedDateStr) {
                return filters.include_missing_listed_date;
            }
            const listedDate = new Date(listedDateStr);
            const startDate = new Date(filters.listed_date_start);
            const endDate = new Date(filters.listed_date_end);
            return listedDate >= startDate && listedDate <= endDate;
        },

        // Filter for rental terms
        termsFilter: function(feature, filters) {
            const terms = feature.properties.data?.terms || [];
            if (!filters.terms_chosen || filters.terms_chosen.length === 0) {
                return true; // If no choices selected, include all
            }
            if (filters.terms_chosen.includes('Unknown') && terms.length === 0) {
                return true;
            }
            return filters.terms_chosen.some(term => terms.includes(term));
        },

        // Filter for laundry features
        laundryFilter: function(feature, filters) {
            const laundry = feature.properties.data?.laundry || 'Unknown';
            if (!filters.laundry_chosen || filters.laundry_chosen.length === 0) {
                return true; // If no choices selected, include all
            }
            if (filters.laundry_chosen.includes('Unknown') && (laundry === null || laundry === undefined)) {
                return true;
            }
            if (filters.laundry_chosen.includes('Other')) {
                const knownCategories = ['In Unit', 'Shared', 'Hookups', 'Included Appliances', 'Location Specific'];
                if (!knownCategories.includes(laundry)) {
                    return true;
                }
            }
            return filters.laundry_chosen.includes(laundry);
        },

        // Filter for property subtypes
        subtypeFilter: function(feature, filters) {
            const subtype = feature.properties.data?.subtype || 'Unknown';
            if (!filters.subtypes_chosen || filters.subtypes_chosen.length === 0) {
                return true; // If no choices selected, include all
            }
            if (filters.subtypes_chosen.includes('Unknown') && (subtype === null || subtype === undefined)) {
                return true;
            }

            // Subtype mapping
            const subtypeMapping = {
                'Apartment': ['Apartment', 'APT'],
                'APT/A': ['APT/A'],
                'APT/D': ['APT/D'],
                'Cabin (Detached)': ['CABIN/D'],
                'Combo - Res & Com': ['Combo - Res & Com', 'Combo - Res &amp; Com'],
                'Commercial Residential (Attached)': ['COMRES/A'],
                'CONDO/A': ['CONDO/A'],
                'CONDO/D': ['CONDO/D'],
                'Condominium': ['Condominium', 'CONDO'],
                'Duplex (Attached)': ['DPLX/A'],
                'Duplex (Detached)': ['DPLX/D'],
                'Loft': ['Loft', 'LOFT'],
                'LOFT/A': ['LOFT/A'],
                'Quadplex (Attached)': ['QUAD/A'],
                'Quadplex (Detached)': ['QUAD/D'],
                'Room For Rent (Attached)': ['RMRT/A'],
                'SFR/A': ['SFR/A'],
                'SFR/D': ['SFR/D'],
                'Single Family': ['Single Family', 'SFR'],
                'Stock Cooperative': ['Stock Cooperative'],
                'Studio (Attached)': ['STUD/A'],
                'Studio (Detached)': ['STUD/D'],
                'Townhouse': ['Townhouse', 'TWNHS'],
                'TWNHS/A': ['TWNHS/A'],
                'TWNHS/D': ['TWNHS/D'],
                'Triplex (Attached)': ['TPLX/A'],
                'Triplex (Detached)': ['TPLX/D'],
                // Add other mappings as needed
            };

            // Expand the selected subtypes based on the mapping
            const selectedSubtypes = new Set();
            filters.subtypes_chosen.forEach(choice => {
                if (subtypeMapping[choice]) {
                    subtypeMapping[choice].forEach(sub => selectedSubtypes.add(sub));
                } else {
                    selectedSubtypes.add(choice);
                }
            });

            return selectedSubtypes.has(subtype);
        },

        // Main GeoJSON filter function
        geojsonFilter: function(feature, context) {
            const filters = context.props.hideout;
            return (
                this.sqftFilter(feature, filters) &&
                this.yrBuiltFilter(feature, filters) &&
                this.garageFilter(feature, filters) &&
                this.ppsqftFilter(feature, filters) &&
                this.petsFilter(feature, filters) &&
                this.furnishedFilter(feature, filters) &&
                this.securityDepositFilter(feature, filters) &&
                this.petDepositFilter(feature, filters) &&
                this.keyDepositFilter(feature, filters) &&
                this.otherDepositFilter(feature, filters) &&
                this.listedDateFilter(feature, filters) &&
                this.termsFilter(feature, filters) &&
                this.laundryFilter(feature, filters) &&
                this.subtypeFilter(feature, filters)
            );
        }
    }
});

// Assign the geojsonFilter function to dashExtensions.default
window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        geojsonFilter: window.dash_clientside.clientside.geojsonFilter
    }
});