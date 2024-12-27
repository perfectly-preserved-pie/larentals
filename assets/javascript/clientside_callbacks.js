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
            petDepositRange,
            petDepositIncludeMissing,
            keyDepositRange,
            keyDepositIncludeMissing,
            otherDepositRange,
            otherDepositIncludeMissing,
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
            const [minPetDeposit, maxPetDeposit] = petDepositRange;
            const [minKeyDeposit, maxKeyDeposit] = keyDepositRange;
            const [minOtherDeposit, maxOtherDeposit] = otherDepositRange;
        
            // Convert the include missing values to booleans
            const sqftIncludeMissingBool = Boolean(sqftIncludeMissing);
            const ppsqftIncludeMissingBool = Boolean(ppsqftIncludeMissing);
            const parkingSpacesIncludeMissingBool = Boolean(parkingSpacesIncludeMissing);
            const yearBuiltIncludeMissingBool = Boolean(yearBuiltIncludeMissing);
            const securityDepositIncludeMissingBool = Boolean(securityDepositIncludeMissing);
            const petDepositIncludeMissingBool = Boolean(petDepositIncludeMissing);
            const keyDepositIncludeMissingBool = Boolean(keyDepositIncludeMissing);
            const otherDepositIncludeMissingBool = Boolean(otherDepositIncludeMissing);
        
            const filteredFeatures = rawData.features.filter(feature => {
                const price = feature.properties.list_price;
                const bedrooms = feature.properties.bedrooms;
                const bathrooms = feature.properties.total_bathrooms;
                const petPolicyValue = feature.properties.pet_policy;
                const sqft = feature.properties.sqft;
                const ppsqft = feature.properties.ppsqft;
                const parkingSpaces = feature.properties.parking_spaces;
                const yearBuilt = feature.properties.year_built;
                const furnished = feature.properties.furnished;
                const securityDeposit = feature.properties.security_deposit;
                const petDeposit = feature.properties.pet_deposit;
                const keyDeposit = feature.properties.key_deposit;
                const otherDeposit = feature.properties.other_deposit;
                const mls_number = feature.properties.mls_number;
        
                let petPolicyFilter = true;
                if (petPolicy === true) {
                    petPolicyFilter = !['No', 'No, Size Limit'].includes(petPolicyValue);
                } else if (petPolicy === false) {
                    petPolicyFilter = ['No', 'No, Size Limit'].includes(petPolicyValue);
                } else if (petPolicy === 'Both') {
                    petPolicyFilter = true;
                }
        
                let sqftFilter = true;
                if (sqftIncludeMissingBool) {
                    sqftFilter = sqft === null || sqft === undefined || (sqft >= minSqft && sqft <= maxSqft);
                } else {
                    sqftFilter = sqft !== null && sqft !== undefined && (sqft >= minSqft && sqft <= maxSqft);
                }
        
                let ppsqftFilter = true;
                if (ppsqftIncludeMissingBool) {
                    ppsqftFilter = ppsqft === null || ppsqft === undefined || (ppsqft >= minPpsqft && ppsqft <= maxPpsqft);
                } else {
                    ppsqftFilter = ppsqft !== null && ppsqft !== undefined && (ppsqft >= minPpsqft && ppsqft <= maxPpsqft);
                }
        
                let parkingFilter = true;
                if (parkingSpacesIncludeMissingBool) {
                    parkingFilter = parkingSpaces === null || parkingSpaces === undefined || (parkingSpaces >= minParking && parkingSpaces <= maxParking);
                } else {
                    parkingFilter = parkingSpaces !== null && parkingSpaces !== undefined && (parkingSpaces >= minParking && parkingSpaces <= maxParking);
                }
                //console.log('Parking filter values:', {
                //    mls_number,
                //    minParking,
                //    maxParking,
                //    parkingSpacesIncludeMissingBool,
                 //   parkingSpaces,
                //    parkingFilter
               // });
        
                let yearBuiltFilter = true;
                if (yearBuiltIncludeMissingBool) {
                    yearBuiltFilter = yearBuilt === null || yearBuilt === undefined || (yearBuilt >= minYear && yearBuilt <= maxYear);
                } else {
                    yearBuiltFilter = yearBuilt !== null && yearBuilt !== undefined && (yearBuilt >= minYear && yearBuilt <= maxYear);
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
                        unknownFilter = !furnished; 
                        chosenFurnished = chosenFurnished.filter(x => x !== "Unknown");
                    }
                    if (chosenFurnished.length > 0) {
                        furnishedFilter = chosenFurnished.includes(furnished) || unknownFilter;
                    } else {
                        furnishedFilter = unknownFilter;
                    }
                }
        
                let securityDepositFilter = true;
                if (securityDepositIncludeMissingBool) {
                    securityDepositFilter = securityDeposit === null || securityDeposit === undefined || (securityDeposit >= minSecurityDeposit && securityDeposit <= maxSecurityDeposit);
                } else {
                    securityDepositFilter = securityDeposit !== null && securityDeposit !== undefined && (securityDeposit >= minSecurityDeposit && securityDeposit <= maxSecurityDeposit);
                }
        
                let petDepositFilter = true;
                if (petDepositIncludeMissingBool) {
                    petDepositFilter = petDeposit === null || petDeposit === undefined || (petDeposit >= minPetDeposit && petDeposit <= maxPetDeposit);
                } else {
                    petDepositFilter = petDeposit !== null && petDeposit !== undefined && (petDeposit >= minPetDeposit && petDeposit <= maxPetDeposit);
                }
                //console.log('Pet deposit filter values:', {
                //    mls_number,
                //    minPetDeposit,
                //    maxPetDeposit,
                //    petDepositIncludeMissingBool,
                //    petDeposit,
                //    petDepositFilter
                //});

                //console.log("Raw value of parkingSpacesIncludeMissing:", parkingSpacesIncludeMissing);
                //console.log("parkingSpacesIncludeMissingBool:", parkingSpacesIncludeMissingBool);

        
                let keyDepositFilter = true;
                if (keyDepositIncludeMissingBool) {
                    keyDepositFilter = keyDeposit === null || keyDeposit === undefined || (keyDeposit >= minKeyDeposit && keyDeposit <= maxKeyDeposit);
                } else {
                    keyDepositFilter = keyDeposit !== null && keyDeposit !== undefined && (keyDeposit >= minKeyDeposit && keyDeposit <= maxKeyDeposit);
                }
        
                let otherDepositFilter = true;
                if (otherDepositIncludeMissingBool) {
                    otherDepositFilter = otherDeposit === null || otherDeposit === undefined || (otherDeposit >= minOtherDeposit && otherDeposit <= maxOtherDeposit);
                } else {
                    otherDepositFilter = otherDeposit !== null && otherDeposit !== undefined && (otherDeposit >= minOtherDeposit && otherDeposit <= maxOtherDeposit);
                }
        
                const includeFeature = price >= minPrice && price <= maxPrice &&
                    bedrooms >= minBedrooms && bedrooms <= maxBedrooms &&
                    bathrooms >= minBathrooms && bathrooms <= maxBathrooms &&
                    petPolicyFilter &&
                    sqftFilter &&
                    ppsqftFilter &&
                    parkingFilter &&
                    yearBuiltFilter &&
                    termsFilter &&
                    furnishedFilter &&
                    securityDepositFilter &&
                    petDepositFilter &&
                    keyDepositFilter &&
                    otherDepositFilter;
        
                if (!includeFeature) {
                    console.log('Feature excluded:', {
                        mls_number,
                        price,
                        bedrooms,
                        bathrooms,
                        petPolicyValue,
                        sqft,
                        ppsqft,
                        parkingSpaces,
                        yearBuilt,
                        furnished,
                        securityDeposit,
                        petDeposit,
                        keyDeposit,
                        otherDeposit,
                        filters: {
                            petPolicyFilter,
                            sqftFilter,
                            ppsqftFilter,
                            parkingFilter,
                            yearBuiltFilter,
                            termsFilter,
                            furnishedFilter,
                            securityDepositFilter,
                            petDepositFilter,
                            keyDepositFilter,
                            otherDepositFilter
                        }
                    });
                }
        
                return includeFeature;
            });
        
            return { type: "FeatureCollection", features: filteredFeatures };
        }
            }
        });