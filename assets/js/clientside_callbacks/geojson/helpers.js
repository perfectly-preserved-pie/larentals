/**
 * @typedef {[number, number]} CoordinatePair
 *
 * @typedef {Object} GeoJSONGeometry
 * @property {string=} type
 * @property {*=} coordinates
 *
 * @typedef {Object} GeoJSONFeature
 * @property {GeoJSONGeometry|null=} geometry
 * @property {Object.<string, *>|null=} properties
 */

/**
 * Convert a value to a finite number when possible.
 *
 * @param {*} value - Candidate numeric value from Dash or GeoJSON properties.
 * @returns {number|null} Parsed number, or null for blank/non-numeric input.
 */
function safeNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const num = Number(value);
    return isNaN(num) ? null : num;
}

/**
 * Normalize a coordinate pair to GeoJSON order: [longitude, latitude].
 *
 * Listing points may arrive as either [lat, lon] or [lon, lat]. This function
 * uses valid latitude/longitude ranges to detect and correct obvious swaps.
 *
 * @param {*} coords - Candidate two-value coordinate array.
 * @returns {CoordinatePair|null} GeoJSON-ordered coordinates, or null if invalid.
 */
function normalizeCoordinatePair(coords) {
    if (!Array.isArray(coords) || coords.length < 2) return null;
    const [a, b] = coords;
    if (typeof a !== "number" || typeof b !== "number") return null;
    // Normalize to [lon, lat] for GeoJSON / turf compatibility
    if (Math.abs(a) <= 90 && Math.abs(b) > 90) return [b, a];  // a=lat, b=lon → [lon, lat]
    if (Math.abs(b) <= 90 && Math.abs(a) > 90) return [a, b];  // a=lon, b=lat → already [lon, lat]
    return [a, b];
}

/**
 * Test whether a speed value falls inside an inclusive numeric range.
 *
 * @param {*} value - Candidate speed value.
 * @param {number} minValue - Inclusive lower bound.
 * @param {number} maxValue - Inclusive upper bound.
 * @param {boolean} includeMissing - Whether blank/non-numeric values should pass.
 * @returns {boolean} True when the value passes the range/missing-value rule.
 */
function speedRangeFilter(value, minValue, maxValue, includeMissing) {
    if (value === null || value === undefined || value === "") {
        return Boolean(includeMissing);
    }
    const num = Number(value);
    if (isNaN(num)) return Boolean(includeMissing);
    return num >= minValue && num <= maxValue;
}

/**
 * Extract a five-digit ZIP code from common listing/crosswalk formats.
 *
 * @param {*} value - Raw ZIP value such as "92805", "92805.0", or "92805-1234".
 * @returns {string} Five-digit ZIP code, or an empty string when unavailable.
 */
function normalizeZipCode(value) {
    if (value === null || value === undefined) return "";
    const match = String(value).trim().match(/\d{5}/);
    return match ? match[0] : "";
}

/**
 * Check whether a listing feature's ZIP code matches any selected ZIP code.
 *
 * This is the fallback for cases where a ZIP is valid for filtering but no
 * polygon is available in the boundary dataset.
 *
 * @param {GeoJSONFeature|null|undefined} feature - Listing point feature.
 * @param {Array<*>} zipCodes - ZIP codes selected by the server-side callback.
 * @returns {boolean} True when the feature's normalized ZIP matches a selected ZIP.
 */
function featureMatchesAnyZip(feature, zipCodes) {
    if (!feature?.properties || !Array.isArray(zipCodes) || !zipCodes.length) {
        return false;
    }

    const listingZip = normalizeZipCode(feature.properties.zip_code);
    if (!listingZip) return false;

    return zipCodes.some((zipCode) => normalizeZipCode(zipCode) === listingZip);
}

/**
 * Check whether a listing point is contained by any selected ZIP polygon.
 *
 * @param {GeoJSONFeature|null|undefined} feature - Listing point feature.
 * @param {Array<GeoJSONFeature>} polygonFeatures - ZIP/ZCTA polygon features.
 * @returns {boolean} True when Turf is available and the point is inside a polygon.
 */
function featureWithinAnyPolygon(feature, polygonFeatures) {
    const turfAvailable = typeof turf !== "undefined" && turf && typeof turf.booleanPointInPolygon === "function";
    if (!turfAvailable || !feature?.geometry || !Array.isArray(polygonFeatures) || !polygonFeatures.length) {
        return false;
    }

    const coords = normalizeCoordinatePair(feature.geometry.coordinates);
    if (!coords) return false;

    const point = turf.point(coords);
    return polygonFeatures.some((polygonFeature) => (
        polygonFeature && polygonFeature.geometry &&
        turf.booleanPointInPolygon(point, polygonFeature)
    ));
}
