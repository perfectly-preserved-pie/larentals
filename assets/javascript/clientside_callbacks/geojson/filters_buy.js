window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
        /**
        * Filters and clusters the GeoJSON data for buying properties based on various criteria.
        * The order of parameters matches the Dash callback's Input order.
        *
        * @param {Array<number>} priceRange - [minPrice, maxPrice] for filtering by `list_price`.
        * @param {Array<number>} bedroomsRange - [minBeds, maxBeds] for filtering by `bedrooms`.
        * @param {Array<number>} bathroomsRange - [minBaths, maxBaths] for filtering by `bathrooms`.
        * @param {Array<number>} sqftRange - [minSqft, maxSqft] for filtering by `sqft`.
        * @param {boolean} sqftIncludeMissing - Whether to include properties with missing `sqft`.
        * @param {Array<number>} ppsqftRange - [minPpsqft, maxPpsqft] for filtering by `ppsqft`.
        * @param {boolean} ppsqftIncludeMissing - Whether to include properties with missing `ppsqft`.
        * @param {Array<number>} lotSizeRange - [minLotSize, maxLotSize] for filtering by `lot_size`.
        * @param {boolean} lotSizeIncludeMissing - Whether to include properties with missing `lot_size`.
        * @param {Array<number>} yearBuiltRange - [minYearBuilt, maxYearBuilt] for filtering by `year_built`.
        * @param {boolean} yearBuiltIncludeMissing - Whether to include properties with missing `year_built`.
        * @param {Array<string>} subtypeSelection - List of selected property `subtype`s.
        * @param {string|null} dateStart - Start date (YYYY-MM-DD) for `listed_date` range.
        * @param {string|null} dateEnd - End date (YYYY-MM-DD) for `listed_date` range.
        * @param {boolean} dateIncludeMissing - Whether to include properties with missing `listed_date`.
         * @param {Array<number>} hoaFeeRange - [minHOA, maxHOA] for filtering by `hoa_fee`.
         * @param {boolean} hoaFeeIncludeMissing - Whether to include properties with missing `hoa_fee`.
         * @param {Array<string>} hoaFeeFrequencyChecklist - Selected options for `hoa_fee_frequency` (e.g., ["N/A", "Monthly"]).
         * @param {Array<number>} downloadSpeedRange - [minDownload, maxDownload] for filtering by `best_dn`.
         * @param {Array<number>} uploadSpeedRange - [minUpload, maxUpload] for filtering by `best_up`.
         * @param {Object} zipBoundaryData - Optional ZIP boundary feature payload.
         * @param {Object} fullGeojson - The full buy GeoJSON data as a FeatureCollection.
        * @returns {Object} A GeoJSON FeatureCollection containing features that match all filters.
        */
        filterAndClusterBuy: function(
            priceRange,
            bedroomsRange,
            bathroomsRange,
            sqftRange,
            sqftIncludeMissing,
            ppsqftRange,
            ppsqftIncludeMissing,
            lotSizeRange,
            lotSizeIncludeMissing,
            yearBuiltRange,
            yearBuiltIncludeMissing,
            subtypeSelection,
            dateStart,
            dateEnd,
            dateIncludeMissing,
            hoaFeeRange,
            hoaFeeIncludeMissing,
            hoaFeeFrequencyChecklist,
            downloadSpeedRange,
            uploadSpeedRange,
            speedIncludeMissing,
            zipBoundaryData,
            fullGeojson
        ) {
            // Guard against missing or malformed GeoJSON
            if (!fullGeojson || !Array.isArray(fullGeojson.features)) {
                return { type: "FeatureCollection", features: [] };
            }
            // Convert Dash boolean inputs to actual booleans
            const sqftIncludeMissingBool           = Boolean(sqftIncludeMissing);
            const ppsqftIncludeMissingBool         = Boolean(ppsqftIncludeMissing);
            const lotSizeIncludeMissingBool        = Boolean(lotSizeIncludeMissing);
            const yearBuiltIncludeMissingBool      = Boolean(yearBuiltIncludeMissing);
            const dateIncludeMissingBool           = Boolean(dateIncludeMissing);
            const hoaFeeIncludeMissingBool         = Boolean(hoaFeeIncludeMissing);

            // Deconstruct range arrays for easier access
            const [minPrice, maxPrice]            = priceRange;
            const [minBedrooms, maxBedrooms]      = bedroomsRange;
            const [minBathrooms, maxBathrooms]    = bathroomsRange;
            const [minSqft, maxSqft]              = sqftRange;
            const [minPpsqft, maxPpsqft]          = ppsqftRange;
            const [minLotSize, maxLotSize]        = lotSizeRange;
            const [minYearBuilt, maxYearBuilt]    = yearBuiltRange;
            const [minHOA, maxHOA]                = hoaFeeRange;
            const normalizedDownloadSpeedRange = Array.isArray(downloadSpeedRange)
                ? downloadSpeedRange
                : [downloadSpeedRange, downloadSpeedRange];
            const normalizedUploadSpeedRange = Array.isArray(uploadSpeedRange)
                ? uploadSpeedRange
                : [uploadSpeedRange, uploadSpeedRange];
            const [minDownloadSpeed, maxDownloadSpeed] = normalizedDownloadSpeedRange;
            const [minUploadSpeed, maxUploadSpeed] = normalizedUploadSpeedRange;
            const speedIncludeMissingBool = Boolean(speedIncludeMissing);
            const zipCodes = Array.isArray(zipBoundaryData?.zip_codes)
                ? zipBoundaryData.zip_codes
                : (zipBoundaryData?.zip_code ? [String(zipBoundaryData.zip_code).trim()] : []);
            const zipFeatures = Array.isArray(zipBoundaryData?.features)
                ? zipBoundaryData.features
                : (zipBoundaryData?.feature ? [zipBoundaryData.feature] : []);
            const shouldFilterByZip = zipFeatures.length > 0 || zipCodes.length > 0;
            const turfAvailable = typeof turf !== "undefined" && turf && typeof turf.booleanPointInPolygon === "function";

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

                // 4) Sqft Filter
                const sqftVal = parseFloat(props.sqft);
                let sqftFilter = !isNaN(sqftVal) && (sqftVal >= minSqft && sqftVal <= maxSqft);
                if (sqftIncludeMissingBool && (props.sqft == null || isNaN(sqftVal))) {
                    sqftFilter = true;
                }

                // 5) PPSqft Filter
                const ppsqftVal = parseFloat(props.ppsqft);
                let ppsqftFilter = !isNaN(ppsqftVal) && (ppsqftVal >= minPpsqft && ppsqftVal <= maxPpsqft);
                if (ppsqftIncludeMissingBool && (props.ppsqft == null || isNaN(ppsqftVal))) {
                    ppsqftFilter = true;
                }

                // 6) Lot Size Filter
                const lotSizeVal = parseFloat(props.lot_size);
                let lotSizeFilter = !isNaN(lotSizeVal) && (lotSizeVal >= minLotSize && lotSizeVal <= maxLotSize);
                if (lotSizeIncludeMissingBool && (props.lot_size == null || isNaN(lotSizeVal))) {
                    lotSizeFilter = true;
                }

                // 7) Year Built Filter
                const yearBuiltVal = parseFloat(props.year_built);
                let yrBuiltFilter = !isNaN(yearBuiltVal) && (yearBuiltVal >= minYearBuilt && yearBuiltVal <= maxYearBuilt);
                if (yearBuiltIncludeMissingBool && (props.year_built == null || isNaN(yearBuiltVal))) {
                    yrBuiltFilter = true;
                }

                // 8) Subtype Filter
                let subtypeFilter = false;
                const propertySubtype = (props.subtype || '').toUpperCase();
                if (propertySubtype === '' && subtypeSelection.includes('Unknown')) {
                    subtypeFilter = true;
                } else {
                    subtypeFilter = subtypeSelection.some(sel => sel.toUpperCase() === propertySubtype);
                }

                // 9) Listed Date Filter
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

                // 10) HOA Fee Filter
                const hoaVal = parseFloat(props.hoa_fee);
                let hoaFilter = !isNaN(hoaVal) && (hoaVal >= minHOA && hoaVal <= maxHOA);
                if (hoaFeeIncludeMissingBool && (props.hoa_fee == null || isNaN(hoaVal))) {
                    hoaFilter = true;
                }

                // 11) HOA Fee Frequency Filter
                const rawVal = props.hoa_fee_frequency;
                const hoaFreqVal = (!rawVal || rawVal === '<NA>') ? 'N/A' : rawVal;
                const hoaFeeFreqFilter = hoaFeeFrequencyChecklist.includes(hoaFreqVal);

                // 12) ISP Speed Filters
                const downloadSpeedFilter = speedRangeFilter(
                    props.best_dn,
                    minDownloadSpeed,
                    maxDownloadSpeed,
                    speedIncludeMissingBool,
                );
                const uploadSpeedFilter = speedRangeFilter(
                    props.best_up,
                    minUploadSpeed,
                    maxUploadSpeed,
                    speedIncludeMissingBool,
                );

                // 13) ZIP boundary filter (Census ZCTA)
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
                    priceInRange &&
                    bedroomsInRange &&
                    bathroomsInRange &&
                    sqftFilter &&
                    ppsqftFilter &&
                    lotSizeFilter &&
                    yrBuiltFilter &&
                    subtypeFilter &&
                    dateFilter &&
                    hoaFilter &&
                    hoaFeeFreqFilter &&
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
