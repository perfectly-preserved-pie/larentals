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
            if (selected_subtype.includes('Manufactured Home')) {
                return {'display': 'block'};
            } else {
                return {'display': 'none'};
            }
        },

        toggleHOAVisibility: function(selected_subtype) {
            if (selected_subtype.includes('Manufactured Home') && selected_subtype.length === 1) {
                return {'display': 'none'};
            } else {
                return {
                    'display': 'block',
                    'marginBottom' : '10px',
                };
            }
        },

        updateDatePicker: function(selectedDays, earliestDate) {
            var today = new Date();
            function formatDate(d) {
                var year = d.getFullYear();
                var month = (d.getMonth() + 1).toString().padStart(2, '0');
                var day = d.getDate().toString().padStart(2, '0');
                return year + '-' + month + '-' + day;
            }
            if (selectedDays > 0) {
                var startDate = new Date();
                startDate.setDate(today.getDate() - parseInt(selectedDays));
                return formatDate(startDate);
            } else {
                // Return the stored earliest date
                return earliestDate;
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
         * @param {Object} fullGeojson - GeoJSON data with .features array
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
            fullGeojson
        ) {
            console.log("fullGeojson type:", typeof fullGeojson, "has features:", !!(fullGeojson && fullGeojson.features));

            if (!fullGeojson || !fullGeojson.features) {
                return {
                    type: "FeatureCollection",
                    features: []
                };
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
            const filteredFeatures = fullGeojson.features.filter(feature => {
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
        * Filters and clusters the GeoJSON data for buying properties based on various criteria.
        * The order of parameters matches the Dash callback's Input order.
        *
        * @param {Array<number>} priceRange - [minPrice, maxPrice] for filtering by `list_price`.
        * @param {Array<number>} bedroomsRange - [minBeds, maxBeds] for filtering by `bedrooms`.
        * @param {Array<number>} bathroomsRange - [minBaths, maxBaths] for filtering by `bathrooms`.
        * @param {boolean|string} petsAllowed - Pet policy choice (`true`, `false`, or `"Both"`).
        * @param {Array<number>} sqftRange - [minSqft, maxSqft] for filtering by `sqft`.
        * @param {boolean} sqftIncludeMissing - Whether to include properties with missing `sqft`.
        * @param {Array<number>} ppsqftRange - [minPpsqft, maxPpsqft] for filtering by `ppsqft`.
        * @param {boolean} ppsqftIncludeMissing - Whether to include properties with missing `ppsqft`.
        * @param {Array<number>} yearBuiltRange - [minYearBuilt, maxYearBuilt] for filtering by `year_built`.
        * @param {boolean} yearBuiltIncludeMissing - Whether to include properties with missing `year_built`.
        * @param {boolean|string} seniorCommunityOption - Senior community choice (`true`, `false`, or `"Both"`).
        * @param {Array<string>} subtypeSelection - List of selected property `subtype`s.
        * @param {string|null} dateStart - Start date (YYYY-MM-DD) for `listed_date` range.
        * @param {string|null} dateEnd - End date (YYYY-MM-DD) for `listed_date` range.
        * @param {boolean} dateIncludeMissing - Whether to include properties with missing `listed_date`.
        * @param {Array<number>} hoaFeeRange - [minHOA, maxHOA] for filtering by `hoa_fee`.
        * @param {boolean} hoaFeeIncludeMissing - Whether to include properties with missing `hoa_fee`.
        * @param {Array<string>} hoaFeeFrequencyChecklist - Selected options for `hoa_fee_frequency` (e.g., ["N/A", "Monthly"]).
        * @param {Array<number>} spaceRentRange - [minSpaceRent, maxSpaceRent] for filtering by `space_rent`.
        * @param {boolean} spaceRentIncludeMissing - Whether to include properties with missing `space_rent`.
        * @param {Object} fullGeojson - The full buy GeoJSON data as a FeatureCollection.
        * @returns {Object} A GeoJSON FeatureCollection containing features that match all filters.
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
            hoaFeeRange,
            hoaFeeIncludeMissing,
            hoaFeeFrequencyChecklist,
            spaceRentRange,
            spaceRentIncludeMissing,
            fullGeojson
        ) {
            // Convert Dash boolean inputs to actual booleans
            const sqftIncludeMissingBool           = Boolean(sqftIncludeMissing);
            const ppsqftIncludeMissingBool         = Boolean(ppsqftIncludeMissing);
            const yearBuiltIncludeMissingBool      = Boolean(yearBuiltIncludeMissing);
            const dateIncludeMissingBool           = Boolean(dateIncludeMissing);
            const hoaFeeIncludeMissingBool         = Boolean(hoaFeeIncludeMissing);
            const spaceRentIncludeMissingBool      = Boolean(spaceRentIncludeMissing);

            // Deconstruct range arrays for easier access
            const [minPrice, maxPrice]            = priceRange;
            const [minBedrooms, maxBedrooms]      = bedroomsRange;
            const [minBathrooms, maxBathrooms]    = bathroomsRange;
            const [minSqft, maxSqft]              = sqftRange;
            const [minPpsqft, maxPpsqft]          = ppsqftRange;
            const [minYearBuilt, maxYearBuilt]    = yearBuiltRange;
            const [minHOA, maxHOA]                = hoaFeeRange;
            const [minSpaceRent, maxSpaceRent]    = spaceRentRange;

            // Debug: Log raw data
            //console.log('Raw data:', fullGeojson);

            // Filter the features based on the provided criteria
            const filteredFeatures = fullGeojson.features.filter((feature) => {
                const props = feature.properties || {};
                const mls_number = props.mls_number || 'Unknown';

                // 1) Price Filter
                const priceVal = parseFloat(props.list_price) || 0;
                const priceInRange = (priceVal >= minPrice && priceVal <= maxPrice);

                // 2) Bedrooms Filter
                const bedroomsVal = parseFloat(props.bedrooms) || 0;
                const bedroomsInRange = (bedroomsVal >= minBedrooms && bedroomsVal <= maxBedrooms);

                // 3) Bathrooms Filter
                const bathroomsVal = parseFloat(props.total_bathrooms) || 0;
                const bathroomsInRange = (bathroomsVal >= minBathrooms && bathroomsVal <= maxBathrooms);

                // 4) Pets Allowed Filter
                let petsFilter = true;
                const petsPolicy = (props.pets_allowed || '').toLowerCase();
                if (petsAllowed === true) {
                    petsFilter = petsPolicy.includes('yes');
                } else if (petsAllowed === false) {
                    petsFilter = petsPolicy.includes('no');
                }
                // If petsAllowed is "Both", do not filter

                // 5) Sqft Filter
                const sqftVal = parseFloat(props.sqft);
                let sqftFilter = !isNaN(sqftVal) && (sqftVal >= minSqft && sqftVal <= maxSqft);
                if (sqftIncludeMissingBool && (props.sqft == null || isNaN(sqftVal))) {
                    sqftFilter = true;
                }

                // 6) PPSqft Filter
                const ppsqftVal = parseFloat(props.ppsqft);
                let ppsqftFilter = !isNaN(ppsqftVal) && (ppsqftVal >= minPpsqft && ppsqftVal <= maxPpsqft);
                if (ppsqftIncludeMissingBool && (props.ppsqft == null || isNaN(ppsqftVal))) {
                    ppsqftFilter = true;
                }

                // 7) Year Built Filter
                const yearBuiltVal = parseFloat(props.year_built);
                let yrBuiltFilter = !isNaN(yearBuiltVal) && (yearBuiltVal >= minYearBuilt && yearBuiltVal <= maxYearBuilt);
                if (yearBuiltIncludeMissingBool && (props.year_built == null || isNaN(yearBuiltVal))) {
                    yrBuiltFilter = true;
                }

                // 8) Senior Community Filter
                let seniorFilter = true;
                const seniorVal = String(props.senior_community).toUpperCase();
                if (seniorCommunityOption === true) {
                    seniorFilter = seniorVal.includes('Y');
                } else if (seniorCommunityOption === false) {
                    seniorFilter = seniorVal.includes('N');
                }
                // If seniorCommunityOption is "Both", do not filter

                // 9) Subtype Filter
                let subtypeFilter = false;
                const propertySubtype = (props.subtype || '').toUpperCase();
                if (propertySubtype === '' && subtypeSelection.includes('Unknown')) {
                    subtypeFilter = true;
                } else {
                    subtypeFilter = subtypeSelection.some(sel => sel.toUpperCase() === propertySubtype);
                }

                // 10) Listed Date Filter
                let dateFilter = false;
                const listedDateStr = props.listed_date || '';
                if (!listedDateStr) {
                    // If missing listed_date, include only if dateIncludeMissing is true
                    dateFilter = !!dateIncludeMissingBool;
                } else {
                    const listedDateObj = new Date(listedDateStr);
                    const startObj = dateStart ? new Date(dateStart) : null;
                    const endObj = dateEnd ? new Date(dateEnd) : null;
                    if (startObj && endObj) {
                        dateFilter = (listedDateObj >= startObj && listedDateObj <= endObj);
                    } else {
                        // If missing start or end, do not constrain
                        dateFilter = true;
                    }
                }

                // 11) HOA Fee Filter
                const hoaVal = parseFloat(props.hoa_fee);
                let hoaFilter = !isNaN(hoaVal) && (hoaVal >= minHOA && hoaVal <= maxHOA);
                if (hoaFeeIncludeMissingBool && (props.hoa_fee == null || isNaN(hoaVal))) {
                    hoaFilter = true;
                }

                // 12) HOA Fee Frequency Filter
                const rawVal = props.hoa_fee_frequency;
                const hoaFreqVal = (!rawVal || rawVal === '<NA>') ? 'N/A' : rawVal;
                const hoaFeeFreqFilter = hoaFeeFrequencyChecklist.includes(hoaFreqVal);

                // 13) Space Rent Filter
                const spaceVal = parseFloat(props.space_rent);
                let spaceRentFilter = !isNaN(spaceVal) && (spaceVal >= minSpaceRent && spaceVal <= maxSpaceRent);
                if (spaceRentIncludeMissingBool && (props.space_rent == null || isNaN(spaceVal))) {
                    spaceRentFilter = true;
                }

                // Combine all filters
                const includeFeature =
                    priceInRange &&
                    bedroomsInRange &&
                    bathroomsInRange &&
                    petsFilter &&
                    sqftFilter &&
                    ppsqftFilter &&
                    yrBuiltFilter &&
                    seniorFilter &&
                    subtypeFilter &&
                    dateFilter &&
                    hoaFilter &&
                    hoaFeeFreqFilter &&
                    spaceRentFilter;

                // Debug if excluded
                if (!includeFeature) {
                    console.log('Feature excluded:', {
                        mls_number,
                        priceVal,
                        bedroomsVal,
                        bathroomsVal,
                        petsAllowed,
                        sqftVal,
                        ppsqftVal,
                        yearBuiltVal,
                        seniorVal,
                        propertySubtype,
                        listedDateStr,
                        hoaVal,
                        hoaFreqVal,
                        spaceVal,
                        filters: {
                            priceInRange,
                            bedroomsInRange,
                            bathroomsInRange,
                            petsFilter,
                            sqftFilter,
                            ppsqftFilter,
                            yrBuiltFilter,
                            seniorFilter,
                            subtypeFilter,
                            dateFilter,
                            hoaFilter,
                            hoaFeeFreqFilter,
                            spaceRentFilter
                        }
                    });
                }

                return includeFeature;
            });

            // Return the filtered FeatureCollection
            return {
                type: "FeatureCollection",
                features: filteredFeatures
            };
        }
    }
});