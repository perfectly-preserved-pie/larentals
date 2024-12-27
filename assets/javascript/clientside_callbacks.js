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
        filterAndCluster: function(
            priceRange,
            bedroomsRange,
            bathroomsRange,
            petPolicy,
            sqftRange,
            sqftIncludeMissing,
            ppsqftRange,
            ppsqftIncludeMissing,
            parkingSpacesRange,
            parkingSpacesIncludeMissing,
            yearBuiltRange,
            yearBuiltIncludeMissing,
            rentalTerms,
            furnishedChoices,
            securityDepositRange,
            securityDepositIncludeMissing,
            rawData
        ) {
            if (!rawData || !rawData.features) {
                return rawData;
            }
        
            const [minPrice, maxPrice] = priceRange;
            const [minBedrooms, maxBedrooms] = bedroomsRange;
            const [minBathrooms, maxBathrooms] = bathroomsRange;
            const [minSqft, maxSqft] = sqftRange;
            const [minPpsqft, maxPpsqft] = ppsqftRange;
            const [minParking, maxParking] = parkingSpacesRange;
            const [minYear, maxYear] = yearBuiltRange;
            const [minSecurityDeposit, maxSecurityDeposit] = securityDepositRange;
        
            const filteredFeatures = rawData.features.filter(feature => {
                const price = feature.properties.list_price || 0;
                const bedrooms = feature.properties.bedrooms || 0;
                const bathrooms = feature.properties.total_bathrooms || 0;
                const petPolicyValue = feature.properties.pet_policy || 'Unknown';
                const sqft = feature.properties.sqft || 0;
                const ppsqft = feature.properties.ppsqft || 0;
                const parkingSpaces = feature.properties.parking_spaces || 0;
                const yearBuilt = feature.properties.year_built || 'Unknown';
                const furnished = feature.properties.furnished || 'Unknown';
                const securityDeposit = feature.properties.security_deposit;
        
                let petPolicyFilter = true;
                if (petPolicy === true) {
                    petPolicyFilter = !['No', 'No, Size Limit'].includes(petPolicyValue);
                } else if (petPolicy === false) {
                    petPolicyFilter = ['No', 'No, Size Limit'].includes(petPolicyValue);
                } else if (petPolicy === 'Both') {
                    petPolicyFilter = true;
                }
        
                let sqftFilter = true;
                if (sqftIncludeMissing) {
                    sqftFilter = !sqft || (sqft >= minSqft && sqft <= maxSqft);
                } else {
                    sqftFilter = sqft && (sqft >= minSqft && sqft <= maxSqft);
                }
        
                let ppsqftFilter = true;
                if (ppsqftIncludeMissing) {
                    ppsqftFilter = !ppsqft || (ppsqft >= minPpsqft && ppsqft <= maxPpsqft);
                } else {
                    ppsqftFilter = ppsqft && (ppsqft >= minPpsqft && ppsqft <= maxPpsqft);
                }
        
                let parkingFilter = true;
                if (parkingSpacesIncludeMissing) {
                    parkingFilter = !parkingSpaces || (parkingSpaces >= minParking && parkingSpaces <= maxParking);
                } else {
                    parkingFilter = parkingSpaces && (parkingSpaces >= minParking && parkingSpaces <= maxParking);
                }
        
                let yearBuiltFilter = true;
                if (yearBuiltIncludeMissing) {
                    yearBuiltFilter = !yearBuilt || (yearBuilt >= minYear && yearBuilt <= maxYear);
                } else {
                    yearBuiltFilter = yearBuilt && (yearBuilt >= minYear && yearBuilt <= maxYear);
                }
        
                let termsFilter = true;
                if (!rentalTerms || rentalTerms.length === 0) {
                    termsFilter = false;
                } else {
                    let unknownFilter = false;
                    let chosenTerms = [...rentalTerms];
                    if (chosenTerms.includes("Unknown")) {
                        unknownFilter = !feature.properties.terms; 
                        chosenTerms = chosenTerms.filter(t => t !== "Unknown");
                    }
                    if (chosenTerms.length > 0) {
                        const pattern = chosenTerms.map(term =>
                            term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
                        ).join("|");
                        const regex = new RegExp(pattern, "i");
                        termsFilter = (feature.properties.terms && regex.test(feature.properties.terms)) || unknownFilter;
                    } else {
                        termsFilter = unknownFilter;
                    }
                }
        
                let furnishedFilter = true;
                if (!furnishedChoices || furnishedChoices.length === 0) {
                    furnishedFilter = false;
                } else {
                    let unknownFilter = false;
                    let chosenFurnished = [...furnishedChoices];
                    if (chosenFurnished.includes("Unknown")) {
                        unknownFilter = !feature.properties.furnished; 
                        chosenFurnished = chosenFurnished.filter(x => x !== "Unknown");
                    }
                    if (chosenFurnished.length > 0) {
                        furnishedFilter = chosenFurnished.includes(feature.properties.furnished) || unknownFilter;
                    } else {
                        furnishedFilter = unknownFilter;
                    }
                }
        
                let securityDepositFilter = true;
                if (securityDepositIncludeMissing) {
                    securityDepositFilter = !securityDeposit || (securityDeposit >= minSecurityDeposit && securityDeposit <= maxSecurityDeposit);
                } else {
                    securityDepositFilter = securityDeposit && (securityDeposit >= minSecurityDeposit && securityDeposit <= maxSecurityDeposit);
                }
        
                return (
                    price >= minPrice && price <= maxPrice &&
                    bedrooms >= minBedrooms && bedrooms <= maxBedrooms &&
                    bathrooms >= minBathrooms && bathrooms <= maxBathrooms &&
                    petPolicyFilter &&
                    sqftFilter &&
                    ppsqftFilter &&
                    parkingFilter &&
                    yearBuiltFilter &&
                    termsFilter &&
                    furnishedFilter &&
                    securityDepositFilter
                );
            });
        
            return { type: "FeatureCollection", features: filteredFeatures };
        }
    }
});