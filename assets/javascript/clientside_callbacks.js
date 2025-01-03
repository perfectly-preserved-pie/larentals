window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        toggleVisibility: function(n_clicks) {
            if (n_clicks === undefined) {
                // PreventUpdate equivalent
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            const displayStyle = (n_clicks % 2 === 0) ? 'block' : 'none';
            const buttonText = (n_clicks % 2 === 0) ? "Hide" : "Show";
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

        /**
         * Filters GeoJSON features according to user-selected criteria.
         *
         * @param {[number, number]} priceRange - [minPrice, maxPrice]
         * @param {[number, number]} bedroomsRange - [minBedrooms, maxBedrooms]
         * @param {[number, number]} bathroomsRange - [minBathrooms, maxBathrooms]
         * @param {boolean|string} petPolicy - User-selected pet policy (true, false, "Both")
         * @param {[number, number]} sqftRange - [minSqft, maxSqft]
         * @param {boolean} sqftIncludeMissing - Whether to include listings with null/undefined sqft
         * @param {[number, number]} ppsqftRange - [minPpsqft, maxPpsqft]
         * @param {boolean} ppsqftIncludeMissing - Whether to include listings with null/undefined ppsqft
         * @param {[number, number]} parkingSpacesRange - [minParking, maxParking]
         * @param {boolean} parkingSpacesIncludeMissing - Whether to include listings with null/undefined parking
         * @param {[number, number]} yearBuiltRange - [minYear, maxYear]
         * @param {boolean} yearBuiltIncludeMissing - Whether to include listings with null/undefined year_built
         * @param {string[]} rentalTerms - Array of user-selected rental terms (e.g. ["12 Months", "Unknown"])
         * @param {string[]} furnishedChoices - Array of furnished options (e.g. ["Furnished", "Unfurnished", "Unknown"])
         * @param {[number, number]} securityDepositRange - [minSecurityDeposit, maxSecurityDeposit]
         * @param {boolean} securityDepositIncludeMissing - Include listings with null/undefined deposit?
         * @param {[number, number]} petDepositRange - [minPetDeposit, maxPetDeposit]
         * @param {boolean} petDepositIncludeMissing - Include listings with null/undefined pet deposit?
         * @param {[number, number]} keyDepositRange - [minKeyDeposit, maxKeyDeposit]
         * @param {boolean} keyDepositIncludeMissing - Include listings with null/undefined key deposit?
         * @param {[number, number]} otherDepositRange - [minOtherDeposit, maxOtherDeposit]
         * @param {boolean} otherDepositIncludeMissing - Include listings with null/undefined other deposit?
         * @param {string[]} laundryChoices - e.g. ["In Unit", "Shared", "Unknown"]
         * @param {string[]} subtypeSelection - e.g. ["Condo", "Townhouse"]
         * @param {string[]} dateRange - e.g. ["2021-01-01", "2021-12-31"]
         * @param {boolean} dateIncludeMissing - Include listings with null/undefined date?
         * @param {Object} rawData - GeoJSON data with .features array
         * @returns {Object} - A GeoJSON FeatureCollection of filtered features
         */
        filterAndCluster: function( // The order here MUST match the order in the callback decorator
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
            laundryChoices,
            subtypeSelection,
            dateStart,
            dateEnd,
            dateIncludeMissing,
            rawData
        ) {
            if (!rawData || !rawData.features) {
                return rawData;
            }

            // Destructure numeric ranges
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

            // Convert the "include missing" flags from dash into booleans
            const sqftIncludeMissingBool           = Boolean(sqftIncludeMissing);
            const ppsqftIncludeMissingBool         = Boolean(ppsqftIncludeMissing);
            const parkingSpacesIncludeMissingBool  = Boolean(parkingSpacesIncludeMissing);
            const yearBuiltIncludeMissingBool      = Boolean(yearBuiltIncludeMissing);
            const securityDepositIncludeMissingBool= Boolean(securityDepositIncludeMissing);
            const petDepositIncludeMissingBool     = Boolean(petDepositIncludeMissing);
            const keyDepositIncludeMissingBool     = Boolean(keyDepositIncludeMissing);
            const otherDepositIncludeMissingBool   = Boolean(otherDepositIncludeMissing);
            const dateIncludeMissingBool           = Boolean(dateIncludeMissing);

            // Convert dateStart and dateEnd to Date objects
            const filterMinDate = dateStart ? new Date(dateStart) : null;
            const filterMaxDate = dateEnd ? new Date(dateEnd) : null;

            // Filter each feature
            const filteredFeatures = rawData.features.filter(feature => {
                // Basic properties
                const price = feature.properties.list_price;
                const bedrooms = feature.properties.bedrooms;
                const bathrooms = feature.properties.total_bathrooms;
                const petPolicyValue = feature.properties.pet_policy;
                const sqft = feature.properties.sqft;
                const ppsqft = feature.properties.ppsqft;
                const parkingSpaces = feature.properties.parking_spaces;
                const yearBuilt = feature.properties.year_built;
                const laundryCategory = feature.properties.laundry_category; 
                const subtype = feature.properties.subtype;
                const date = feature.properties.listed_date;
                const mls_number = feature.properties.mls_number;

                // Transform "Both" -> "Furnished Or Unfurnished"
                let furnished = feature.properties.furnished;
                if (furnished === "Both") {
                    furnished = "Furnished Or Unfurnished";
                }

                // Deposits
                const securityDeposit = feature.properties.security_deposit;
                const petDeposit = feature.properties.pet_deposit;
                const keyDeposit = feature.properties.key_deposit;
                const otherDeposit = feature.properties.other_deposit;

                // 1) petPolicyFilter
                let petPolicyFilter = true;
                if (petPolicy === true) {
                    petPolicyFilter = !['No', 'No, Size Limit'].includes(petPolicyValue);
                } else if (petPolicy === false) {
                    petPolicyFilter = ['No', 'No, Size Limit'].includes(petPolicyValue);
                } else if (petPolicy === 'Both') {
                    petPolicyFilter = true;
                }

                // 2) sqftFilter
                let sqftFilter = true;
                if (sqftIncludeMissingBool) {
                    sqftFilter = (sqft === null || sqft === undefined) ||
                                 (sqft >= minSqft && sqft <= maxSqft);
                } else {
                    sqftFilter = (sqft !== null && sqft !== undefined) &&
                                 (sqft >= minSqft && sqft <= maxSqft);
                }

                // 3) ppsqftFilter
                let ppsqftFilter = true;
                if (ppsqftIncludeMissingBool) {
                    ppsqftFilter = (ppsqft === null || ppsqft === undefined) ||
                                   (ppsqft >= minPpsqft && ppsqft <= maxPpsqft);
                } else {
                    ppsqftFilter = (ppsqft !== null && ppsqft !== undefined) &&
                                   (ppsqft >= minPpsqft && ppsqft <= maxPpsqft);
                }

                // 4) parkingFilter
                let parkingFilter = true;
                if (parkingSpacesIncludeMissingBool) {
                    parkingFilter = (parkingSpaces === null || parkingSpaces === undefined) ||
                                    (parkingSpaces >= minParking && parkingSpaces <= maxParking);
                } else {
                    parkingFilter = (parkingSpaces !== null && parkingSpaces !== undefined) &&
                                    (parkingSpaces >= minParking && parkingSpaces <= maxParking);
                }

                // 5) yearBuiltFilter
                let yearBuiltFilter = true;
                if (yearBuiltIncludeMissingBool) {
                    yearBuiltFilter = (yearBuilt === null || yearBuilt === undefined) ||
                                      (yearBuilt >= minYear && yearBuilt <= maxYear);
                } else {
                    yearBuiltFilter = (yearBuilt !== null && yearBuilt !== undefined) &&
                                      (yearBuilt >= minYear && yearBuilt <= maxYear);
                }

                // 6) termsFilter
                let termsFilter = true;
                if (!rentalTerms || rentalTerms.length === 0) {
                    termsFilter = false;
                } else {
                    let unknownFilter = false;
                    let chosenTerms = [...rentalTerms];
                    if (chosenTerms.includes("Unknown")) {
                        // If user wants "Unknown," pass if no terms
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

                // 7) furnishedFilter
                let furnishedFilter = true;
                if (!furnishedChoices || furnishedChoices.length === 0) {
                    furnishedFilter = false;
                } else {
                    let unknownFilter = false;
                    let chosenFurnished = [...furnishedChoices];
                    if (chosenFurnished.includes("Unknown")) {
                        unknownFilter = (furnished === null ||
                                         furnished === undefined ||
                                         furnished === "Unknown");
                        chosenFurnished = chosenFurnished.filter(x => x !== "Unknown");
                    }
                    if (chosenFurnished.length > 0) {
                        furnishedFilter = chosenFurnished.includes(furnished) || unknownFilter;
                    } else {
                        furnishedFilter = unknownFilter;
                    }
                }

                // 8) securityDepositFilter
                let securityDepositFilter = true;
                if (securityDepositIncludeMissingBool) {
                    securityDepositFilter = (securityDeposit === null || securityDeposit === undefined) ||
                                            (securityDeposit >= minSecurityDeposit && securityDeposit <= maxSecurityDeposit);
                } else {
                    securityDepositFilter = (securityDeposit !== null && securityDeposit !== undefined) &&
                                            (securityDeposit >= minSecurityDeposit && securityDeposit <= maxSecurityDeposit);
                }

                // 9) petDepositFilter
                let petDepositFilter = true;
                if (petDepositIncludeMissingBool) {
                    petDepositFilter = (petDeposit === null || petDeposit === undefined) ||
                                       (petDeposit >= minPetDeposit && petDeposit <= maxPetDeposit);
                } else {
                    petDepositFilter = (petDeposit !== null && petDeposit !== undefined) &&
                                       (petDeposit >= minPetDeposit && petDeposit <= maxPetDeposit);
                }

                // 10) keyDepositFilter
                let keyDepositFilter = true;
                if (keyDepositIncludeMissingBool) {
                    keyDepositFilter = (keyDeposit === null || keyDeposit === undefined) ||
                                       (keyDeposit >= minKeyDeposit && keyDeposit <= maxKeyDeposit);
                } else {
                    keyDepositFilter = (keyDeposit !== null && keyDeposit !== undefined) &&
                                       (keyDeposit >= minKeyDeposit && keyDeposit <= maxKeyDeposit);
                }

                // 11) otherDepositFilter
                let otherDepositFilter = true;
                if (otherDepositIncludeMissingBool) {
                    otherDepositFilter = (otherDeposit === null || otherDeposit === undefined) ||
                                         (otherDeposit >= minOtherDeposit && otherDeposit <= maxOtherDeposit);
                } else {
                    otherDepositFilter = (otherDeposit !== null && otherDeposit !== undefined) &&
                                         (otherDeposit >= minOtherDeposit && otherDeposit <= maxOtherDeposit);
                }

                // 12) laundryFilter - now referencing standardized laundry_category
                let laundryFilter = true;
                if (!laundryChoices || laundryChoices.length === 0) {
                    // user unchecked everything => exclude all
                    laundryFilter = false;
                } else {
                    let unknownLaundryOk = false;
                    let chosenLaundry = [...laundryChoices];

                    // If user includes "Unknown" as a choice
                    if (chosenLaundry.includes("Unknown")) {
                        unknownLaundryOk = (
                            laundryCategory === null ||
                            laundryCategory === undefined ||
                            laundryCategory === "Unknown"
                        );
                        chosenLaundry = chosenLaundry.filter(x => x !== "Unknown");
                    }

                    // Now do a simple membership check
                    // If user choices includes the listing's laundryCategory, or it's unknown
                    laundryFilter = chosenLaundry.includes(laundryCategory) || unknownLaundryOk;
                }

                // 13) subtypeFilter - referencing the new flattened subtype values
                let subtypeFilterResult = true;
                if (!subtypeSelection || subtypeSelection.length === 0) {
                    // If user unchecks everything => exclude all
                    subtypeFilterResult = false;
                } else {
                    let unknownSubtypeOk = false;
                    let chosenSubtypes = [...subtypeSelection];

                    // If user includes "Unknown" as a choice
                    if (chosenSubtypes.includes("Unknown")) {
                        unknownSubtypeOk = (
                            subtype === null ||
                            subtype === undefined ||
                            subtype === "Unknown"
                        );
                        chosenSubtypes = chosenSubtypes.filter(x => x !== "Unknown");
                    }

                    // Now do a simple membership check:
                    // If user choices includes the listing's flattened subtype, or it's unknown
                    subtypeFilterResult = chosenSubtypes.includes(subtype) || unknownSubtypeOk;
                }

                // 14) dateFilter
                let dateFilter = true;
                const listingDate = date ? new Date(date) : null;
                if (dateIncludeMissingBool) {
                    dateFilter = (listingDate === null) ||
                                 (listingDate >= filterMinDate && listingDate <= filterMaxDate);
                } else {
                    dateFilter = (listingDate !== null) &&
                                 (listingDate >= filterMinDate && listingDate <= filterMaxDate);
                }

                // Decide if we include this feature
                const includeFeature =
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
                    securityDepositFilter &&
                    petDepositFilter &&
                    keyDepositFilter &&
                    otherDepositFilter &&
                    laundryFilter &&
                    subtypeFilterResult &&
                    dateFilter;

                // Debug if excluded
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
                        laundryCategory,
                        subtype,
                        date,
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
                            otherDepositFilter,
                            laundryFilter,
                            subtypeFilterResult,
                            dateFilter
                        }
                    });
                }

                return includeFeature;
            });

            // Return new FeatureCollection
            return { type: "FeatureCollection", features: filteredFeatures };
        },
        /**
         * Filters and clusters the GeoJSON data for buying properties, following the logic
         * in the BuyFilters class. The order of parameters matches the Dash callback's Input order.
         *
         * @param {Array<number>} priceRange - [minPrice, maxPrice] for filtering by list_price.
         * @param {Array<number>} bedroomsRange - [minBeds, maxBeds] for filtering by bedrooms.
         * @param {Array<number>} bathroomsRange - [minBaths, maxBaths] for filtering by bathrooms.
         * @param {string|boolean} petsAllowed - The pet policy choice from the user (could be true, false, or "Both").
         * @param {Array<number>} sqftRange - [minSqft, maxSqft] for filtering by sqft.
         * @param {boolean} sqftIncludeMissing - Whether to include rows where sqft is missing (null or "Unknown").
         * @param {Array<number>} ppsqftRange - [minPpSqft, maxPpSqft] for filtering by ppsqft.
         * @param {boolean} ppsqftIncludeMissing - Whether to include rows where ppsqft is missing.
         * @param {Array<number>} garageSpacesRange - Placeholder for garage spaces filtering (not in df columns).
         * @param {boolean} garageSpacesIncludeMissing - Placeholder for including missing garage spaces (not in df).
         * @param {Array<number>} yearBuiltRange - [yearBuiltStart, yearBuiltEnd] for filtering by year_built.
         * @param {boolean} yearBuiltIncludeMissing - Whether to include rows with missing year_built.
         * @param {string|boolean} seniorCommunityOption - The senior community choice (true, false, or "Both").
         * @param {Array<string>} subtypeSelection - List of selected subtypes (e.g., ["SFR", "MH"]).
         * @param {string} dateStart - The listing date range start (YYYY-MM-DD).
         * @param {string} dateEnd - The listing date range end (YYYY-MM-DD).
         * @param {boolean} dateIncludeMissing - Whether to include rows with a missing listed_date.
         * @param {Object} rawData - The full buy GeoJSON data.
         * @returns {Object} A GeoJSON FeatureCollection with features that match all filters.
         */
        filterAndClusterBuy: function(
            priceRange,
            bedroomsRange,
            bathroomsRange,
            petsAllowed,
            sqftRange,
            sqftIncludeMissing,
            ppsqftRange,
            ppsqftIncludeMissing,
            yearBuiltRange,
            yearBuiltIncludeMissing,
            seniorCommunityOption,
            subtypeSelection,
            dateStart,
            dateEnd,
            dateIncludeMissing,
            rawData
        ) {
            if (!rawData || !rawData.features) {
                return rawData;
            }

            // Destructure numeric ranges
            const [minPrice, maxPrice] = priceRange;
            const [minBedrooms, maxBedrooms] = bedroomsRange;
            const [minBathrooms, maxBathrooms] = bathroomsRange;
            const [minSqft, maxSqft] = sqftRange;
            const [minPpsqft, maxPpsqft] = ppsqftRange;
            //const [minParking, maxParking] = parkingSpacesRange;
            const [minYear, maxYear] = yearBuiltRange;

            // Convert the "include missing" flags from dash into booleans
            const sqftIncludeMissingBool           = Boolean(sqftIncludeMissing);
            const ppsqftIncludeMissingBool         = Boolean(ppsqftIncludeMissing);
            const yearBuiltIncludeMissingBool      = Boolean(yearBuiltIncludeMissing);
            const dateIncludeMissingBool           = Boolean(dateIncludeMissing);

            console.log('Raw data:', rawData);

            const filteredFeatures = rawData.features.filter((feature) => {
            const props = feature.properties || {};
        
            // 1) priceFilter (list_price)
            const priceVal = parseFloat(props.list_price) || 0;
            const priceInRange = (priceVal >= priceRange[0]) && (priceVal <= priceRange[1]);
        
            // 2) bedroomsFilter
            const bedroomsVal = parseFloat(props.bedrooms) || 0;
            const bedroomsInRange = (bedroomsVal >= bedroomsRange[0]) && (bedroomsVal <= bedroomsRange[1]);
        
            // 3) bathroomsFilter
            const bathroomsVal = parseFloat(props.bathrooms) || 0;
            const bathroomsInRange = (bathroomsVal >= bathroomsRange[0]) && (bathroomsVal <= bathroomsRange[1]);
        
            // 4) petsAllowedFilter (pets_allowed column)
            // BuyFilters often distinguishes "Yes", "No", etc., or includes logic for "MH" subtype,
            // but we'll mimic a simpler approach here. 
            let petsFilter = true;
            const petPolicy = (props.pets_allowed || '').toLowerCase();  
            // If user wants properties that allow pets
            if (petsAllowed === true) {
                petsFilter = petPolicy.includes('yes');
            } else if (petsAllowed === false) {
                petsFilter = petPolicy.includes('no');
            } 
            // if petsAllowed === "Both", we do not filter by pet policy
        
            // 5) sqftFilter
            // If sqftIncludeMissing is true, we include rows with missing or "Unknown" sqft
            const sqftVal = parseFloat(props.sqft) || 0;
            // If the user chose to include missing values:
            let sqftFilter = (sqftVal >= minSqft && sqftVal <= maxSqft);
            if (sqftIncludeMissingBool && (props.sqft === null || isNaN(sqftVal))) {
                sqftFilter = true;
            }
        
            // 6) ppsqftFilter
            let ppsqftVal = parseFloat(props.ppsqft) || 0;
            let ppsqftFilter = (ppsqftVal >= ppsqftRange[0]) && (ppsqftVal <= ppsqftRange[1]);
            if (ppsqftIncludeMissingBool && (props.ppsqft === null || isNaN(ppsqftVal))) {
                ppsqftFilter = true;
            }
        
            // 8) yearBuiltFilter
            let yearBuiltVal = parseFloat(props.year_built) || 0;
            let yrBuiltFilter = (yearBuiltVal >= yearBuiltRange[0]) && (yearBuiltVal <= yearBuiltRange[1]);
            if (yearBuiltIncludeMissingBool && (props.year_built === null || isNaN(yearBuiltVal))) {
                yrBuiltFilter = true;
            }
        
            // 9) seniorCommunityFilter (senior_community column with "Y"/"N")
            let seniorFilter = true;
            const seniorVal = (props.senior_community || '').toUpperCase();
            if (seniorCommunityOption === true) {
                seniorFilter = seniorVal.includes('Y');
            } else if (seniorCommunityOption === false) {
                seniorFilter = seniorVal.includes('N');
            } 
            // if seniorCommunityOption === "Both", we do not filter by senior_community
        
            // 10) subtypeFilter
            // If "Unknown" is in subtypeSelection, include null or empty. Otherwise, match subtypes
            let subtypeFilter = false;
            let propertySubtype = (props.subtype || '').toUpperCase();
            if (propertySubtype === '' && subtypeSelection.includes('Unknown')) {
                subtypeFilter = true;
            } else {
                // Check whether the propertySubtype is in user selections (case-insensitive)
                subtypeFilter = subtypeSelection.some(sel => sel.toUpperCase() === propertySubtype);
            }
        
            // 11) listedDateFilter
            // If dateIncludeMissing is true, we allow missing or out-of-range dates
            // We'll parse listed_date as a Date
            let dateFilter = false;
            const listedDateStr = props.listed_date || '';
            if (!listedDateStr) {
                // If there's no listed_date, include only if dateIncludeMissing is true
                dateFilter = !!dateIncludeMissingBool;
            } else {
                // Convert to JS Date and compare
                const listedDateObj = new Date(listedDateStr);
                const startObj = dateStart ? new Date(dateStart) : null;
                const endObj = dateEnd ? new Date(dateEnd) : null;
        
                if (startObj && endObj) {
                dateFilter = (listedDateObj >= startObj && listedDateObj <= endObj);
                } else {
                // If missing either start or end, assume the user wants everything
                dateFilter = true;
                }
            }

            // Decide if we include this feature
            const includeFeature =
                priceVal >= minPrice && priceVal <= maxPrice &&
                bedroomsVal >= minBedrooms && bedroomsVal <= maxBedrooms &&
                bathroomsVal >= minBathrooms && bathroomsVal <= maxBathrooms &&
                petsFilter &&
                sqftFilter &&
                ppsqftFilter &&
                yrBuiltFilter &&
                subtypeFilter &&
                dateFilter;

            // Debug if excluded
            if (!includeFeature) {
                console.log('Feature excluded:', {
                    mls_number,
                    priceVal,
                    bedroomsVal,
                    bathroomsVal,
                    petPolicyValue,
                    sqft,
                    ppsqft,
                    yearBuiltVal,
                    subtype,
                    date,
                    filters: {
                        petPolicyFilter,
                        sqftFilter,
                        ppsqftFilter,
                        yrBuiltFilter,
                        subtypeFilter,
                        dateFilter
                    }
                });
            }
        
            // Combine all filters
            return (
                priceInRange &&
                bedroomsInRange &&
                bathroomsInRange &&
                petsFilter &&
                sqftFilter &&
                ppsqftFilter &&
                yrBuiltFilter &&
                seniorFilter &&
                subtypeFilter &&
                dateFilter
            );
            });
        
            return {
            type: 'FeatureCollection',
            features: filteredFeatures
            };
        }
    }
});