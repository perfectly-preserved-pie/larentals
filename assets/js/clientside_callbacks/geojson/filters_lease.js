window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
        /**
         * Filters GeoJSON features according to user-selected criteria (lease page).
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
         * @param {string[]} rentalTerms - Array of user-selected rental terms
         * @param {boolean} termsIncludeMissing - Include listings with null/undefined terms?
         * @param {string[]} furnishedChoices - Array of furnished options
         * @param {[number, number]} securityDepositRange - [minSecurityDeposit, maxSecurityDeposit]
         * @param {boolean} securityDepositIncludeMissing - Include listings with null/undefined deposit?
         * @param {[number, number]} petDepositRange - [minPetDeposit, maxPetDeposit]
         * @param {boolean} petDepositIncludeMissing - Include listings with null/undefined pet deposit?
         * @param {[number, number]} keyDepositRange - [minKeyDeposit, maxKeyDeposit]
         * @param {boolean} keyDepositIncludeMissing - Include listings with null/undefined key deposit?
         * @param {[number, number]} otherDepositRange - [minOtherDeposit, maxOtherDeposit]
         * @param {boolean} otherDepositIncludeMissing - Include listings with null/undefined other deposit?
         * @param {string[]} laundryChoices - Array of selected laundry categories
         * @param {string[]} subtypeSelection - List of selected property subtypes
         * @param {string|null} dateStart - Start date (YYYY-MM-DD) for listed_date range
         * @param {string|null} dateEnd - End date (YYYY-MM-DD) for listed_date range
         * @param {boolean} dateIncludeMissing - Whether to include properties with missing listed_date
         * @param {[number, number]} downloadSpeedRange - [minDownload, maxDownload]
         * @param {[number, number]} uploadSpeedRange - [minUpload, maxUpload]
         * @param {boolean} speedIncludeMissing - Whether to include listings with missing ISP speeds
         * @param {Object} zipBoundaryData - Optional ZIP boundary feature payload
         * @param {Object} fullGeojson - GeoJSON data with .features array
         * @returns {Object} - A GeoJSON FeatureCollection of filtered features
         */
        filterAndClusterLease: function(
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
            termsIncludeMissing,
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
            downloadSpeedRange,
            uploadSpeedRange,
            speedIncludeMissing,
            zipBoundaryData,
            fullGeojson
        ) {
            if (!fullGeojson || !fullGeojson.features) {
                return window.dash_clientside.no_update;
            }

            // Deconstruct range arrays
            const [minPrice, maxPrice]           = priceRange;
            const [minBedrooms, maxBedrooms]     = bedroomsRange;
            const [minBathrooms, maxBathrooms]   = bathroomsRange;
            const [minSqft, maxSqft]             = sqftRange;
            const [minPpsqft, maxPpsqft]         = ppsqftRange;
            const [minParking, maxParking]        = parkingSpacesRange;
            const [minYear, maxYear]             = yearBuiltRange;
            const [minSecurityDeposit, maxSecurityDeposit] = securityDepositRange;
            const [minPetDeposit, maxPetDeposit]           = petDepositRange;
            const [minKeyDeposit, maxKeyDeposit]           = keyDepositRange;
            const [minOtherDeposit, maxOtherDeposit]       = otherDepositRange;

            const normalizedDownloadSpeedRange = Array.isArray(downloadSpeedRange)
                ? downloadSpeedRange
                : [downloadSpeedRange, downloadSpeedRange];
            const normalizedUploadSpeedRange = Array.isArray(uploadSpeedRange)
                ? uploadSpeedRange
                : [uploadSpeedRange, uploadSpeedRange];
            const [minDownloadSpeed, maxDownloadSpeed] = normalizedDownloadSpeedRange;
            const [minUploadSpeed, maxUploadSpeed] = normalizedUploadSpeedRange;

            // ZIP boundary setup
            const zipCodes = Array.isArray(zipBoundaryData?.zip_codes)
                ? zipBoundaryData.zip_codes
                : (zipBoundaryData?.zip_code ? [String(zipBoundaryData.zip_code).trim()] : []);
            const zipFeatures = Array.isArray(zipBoundaryData?.features)
                ? zipBoundaryData.features
                : (zipBoundaryData?.feature ? [zipBoundaryData.feature] : []);
            const shouldFilterByZip = zipFeatures.length > 0 || zipCodes.length > 0;
            const turfAvailable = typeof turf !== "undefined" && turf && typeof turf.booleanPointInPolygon === "function";

            // Convert "include missing" flags to booleans
            const sqftIncludeMissingBool            = Boolean(sqftIncludeMissing);
            const ppsqftIncludeMissingBool          = Boolean(ppsqftIncludeMissing);
            const parkingSpacesIncludeMissingBool   = Boolean(parkingSpacesIncludeMissing);
            const yearBuiltIncludeMissingBool       = Boolean(yearBuiltIncludeMissing);
            const termsIncludeMissingBool           = Boolean(termsIncludeMissing);
            const securityDepositIncludeMissingBool = Boolean(securityDepositIncludeMissing);
            const petDepositIncludeMissingBool      = Boolean(petDepositIncludeMissing);
            const keyDepositIncludeMissingBool      = Boolean(keyDepositIncludeMissing);
            const otherDepositIncludeMissingBool    = Boolean(otherDepositIncludeMissing);
            const dateIncludeMissingBool            = Boolean(dateIncludeMissing);
            const speedIncludeMissingBool           = Boolean(speedIncludeMissing);

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
                const downloadSpeed = feature.properties.best_dn;
                const uploadSpeed = feature.properties.best_up;
                const termsValueRaw = feature.properties.terms;
                // Normalize terms: null/undefined stay null, non-null strings are trimmed.
                const termsValue = (termsValueRaw === null || termsValueRaw === undefined)
                    ? null
                    : String(termsValueRaw).trim();
                const isTermsMissing = (termsValue === null || termsValue === "");

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
                    termsFilter = termsIncludeMissingBool ? isTermsMissing : false;
                } else {
                    // Normalize and remove empty values
                    let chosenTerms = [...rentalTerms].filter(t => t && String(t).trim().length > 0);

                    // Include missing terms only if the listing is missing terms AND
                    // the "include missing" switch is on
                    const unknownFilter = isTermsMissing && termsIncludeMissingBool;

                    if (chosenTerms.length > 0) {
                        const pattern = chosenTerms.map(term =>
                            term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
                        ).join("|");
                        const regex = new RegExp(pattern, "i");
                        termsFilter = (termsValue !== null && termsValue !== "" && regex.test(termsValue)) || unknownFilter;
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
                        unknownFilter = (furnished === null || furnished === undefined || furnished === "" || furnished === "Unknown");
                        chosenFurnished = chosenFurnished.filter(x => x !== "Unknown");
                    }
                    furnishedFilter = chosenFurnished.includes(furnished) || unknownFilter;
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

                // 12) laundryFilter
                let laundryFilter = true;
                if (!laundryChoices || laundryChoices.length === 0) {
                    laundryFilter = false;
                } else {
                    let unknownLaundryOk = false;
                    let chosenLaundry = [...laundryChoices];
                    if (chosenLaundry.includes("Unknown")) {
                        unknownLaundryOk = (
                            laundryCategory === null ||
                            laundryCategory === undefined ||
                            laundryCategory === "Unknown"
                        );
                        chosenLaundry = chosenLaundry.filter(x => x !== "Unknown");
                    }
                    laundryFilter = chosenLaundry.includes(laundryCategory) || unknownLaundryOk;
                }

                // 13) subtypeFilter
                let subtypeFilter = true;
                if (subtypeSelection && subtypeSelection.length > 0) {
                    subtypeFilter = subtypeSelection.includes(subtype);
                }

                // 14) priceFilter, bedroomsFilter, bathroomsFilter
                const priceFilter = (price >= minPrice && price <= maxPrice);
                const bedroomsFilter = (bedrooms >= minBedrooms && bedrooms <= maxBedrooms);
                const bathroomsFilter = (bathrooms >= minBathrooms && bathrooms <= maxBathrooms);

                // 15) dateFilter
                let dateFilter = true;
                const listingDate = date ? new Date(date) : null;
                if (dateIncludeMissingBool) {
                    dateFilter = (listingDate === null) ||
                                 (listingDate >= filterMinDate && listingDate <= filterMaxDate);
                } else {
                    dateFilter = (listingDate !== null) &&
                                 (listingDate >= filterMinDate && listingDate <= filterMaxDate);
                }

                // 16) ISP speed filters
                const downloadSpeedFilter = speedRangeFilter(
                    downloadSpeed,
                    minDownloadSpeed,
                    maxDownloadSpeed,
                    speedIncludeMissingBool,
                );
                const uploadSpeedFilter = speedRangeFilter(
                    uploadSpeed,
                    minUploadSpeed,
                    maxUploadSpeed,
                    speedIncludeMissingBool,
                );

                // 17) ZIP boundary filter (Census ZCTA)
                let zipFilter = true;
                if (shouldFilterByZip) {
                    if (!zipFeatures.length || !turfAvailable || !feature.geometry) {
                        return false;
                    }
                    const coords = normalizeCoordinatePair(feature.geometry.coordinates);
                    if (!coords) {
                        return false;
                    }
                    const point = turf.point(coords);
                    zipFilter = zipFeatures.some((zipFeature) => (
                        zipFeature && zipFeature.geometry &&
                        turf.booleanPointInPolygon(point, zipFeature)
                    ));
                }

                // Combine all filters
                const includeFeature =
                    priceFilter &&
                    bedroomsFilter &&
                    bathroomsFilter &&
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
                    subtypeFilter &&
                    dateFilter &&
                    downloadSpeedFilter &&
                    uploadSpeedFilter &&
                    zipFilter;

                return includeFeature;
            });

            // Return the filtered FeatureCollection
            return {
                type: "FeatureCollection",
                features: filteredFeatures
            };
        }
    })
});