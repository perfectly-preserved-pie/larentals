function safeNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const num = Number(value);
    return isNaN(num) ? null : num;
}

function emptyFeatureCollection() {
    return { type: "FeatureCollection", features: [] };
}

function normalizeCoordinatePair(coords) {
    if (!Array.isArray(coords) || coords.length < 2) return null;
    const [a, b] = coords;
    if (typeof a !== "number" || typeof b !== "number") return null;
    // Normalize to [lon, lat] for GeoJSON / turf compatibility
    if (Math.abs(a) <= 90 && Math.abs(b) > 90) return [b, a];  // a=lat, b=lon → [lon, lat]
    if (Math.abs(b) <= 90 && Math.abs(a) > 90) return [a, b];  // a=lon, b=lat → already [lon, lat]
    return [a, b];
}

function speedRangeFilter(value, minValue, maxValue, includeMissing) {
    if (value === null || value === undefined || value === "") {
        return Boolean(includeMissing);
    }
    const num = Number(value);
    if (isNaN(num)) return Boolean(includeMissing);
    return num >= minValue && num <= maxValue;
}

function normalizeListingId(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim().replace(/\.0$/, "");
}

function normalizeListingIdSet(values) {
    return new Set(
        Array.isArray(values)
            ? values.map((value) => normalizeListingId(value)).filter((value) => value.length > 0)
            : []
    );
}

function buildCommuteCandidateSignature(commuteSignature, featureCollection) {
    if (!commuteSignature || !Array.isArray(featureCollection?.features)) {
        return null;
    }

    const normalizedIds = featureCollection.features
        .map((feature) => normalizeListingId(feature?.properties?.mls_number))
        .filter((value) => value.length > 0)
        .sort();

    return `${commuteSignature}|${normalizedIds.join(",")}`;
}

function filterFeatureCollectionByListingIds(featureCollection, eligibleListingIds) {
    if (!Array.isArray(featureCollection?.features)) {
        return emptyFeatureCollection();
    }

    const eligibleSet = normalizeListingIdSet(eligibleListingIds);

    return {
        type: "FeatureCollection",
        features: featureCollection.features.filter((feature) => eligibleSet.has(
            normalizeListingId(feature?.properties?.mls_number)
        )),
    };
}

function cloneFeatureWithCommuteState(feature, matchState, statusText) {
    const properties = feature && typeof feature.properties === "object" && feature.properties !== null
        ? feature.properties
        : {};

    return Object.assign({}, feature, {
        properties: Object.assign({}, properties, {
            commute_match_state: matchState || null,
            commute_status_text: statusText || null,
        }),
    });
}

function commuteStateSortRank(matchState) {
    if (matchState === "verified_match") return 0;
    if (matchState === "rough_match") return 1;
    if (matchState === "verified_excluded") return 2;
    return 3;
}

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
