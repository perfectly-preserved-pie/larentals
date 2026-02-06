function safeNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const num = Number(value);
    return isNaN(num) ? null : num;
}

function normalizeCoordinatePair(coords) {
    if (!Array.isArray(coords) || coords.length < 2) return null;
    const [a, b] = coords;
    if (typeof a !== "number" || typeof b !== "number") return null;
    if (Math.abs(a) <= 90 && Math.abs(b) > 90) return [a, b];
    if (Math.abs(b) <= 90 && Math.abs(a) > 90) return [b, a];
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