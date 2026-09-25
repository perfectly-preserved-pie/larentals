(function () {
    "use strict";

    const root = window.larentals = window.larentals || {};
    const filters = root.filters = root.filters || {};
    const homeTypeGroups = Object.freeze({
        "group:single_family": ["Single Family Residence"],
        "group:apartment": ["Apartment", "Studio", "Loft"],
        "group:condo": ["Condominium", "Stock Cooperative", "Own Your Own"],
        "group:townhouse": ["Townhouse"],
        "group:small_multi": ["Duplex", "Triplex", "Quadplex"],
    });
    const groupedTypes = new Set(Object.values(homeTypeGroups).flat().map(type => type.toLowerCase()));

    /**
     * Match a broad home-type choice or an exact MLS subtype.
     * Unknown and uncommon types stay separate so a broad selection does not
     * silently include listings whose physical type was never reported.
     * @param {*} subtype Listing subtype supplied by GeoJSON.
     * @param {string[]} selected User-selected group or exact subtype values.
     * @returns {boolean} Whether this listing matches at least one choice.
     */
    filters.matchesHomeType = function (subtype, selected) {
        if (!Array.isArray(selected) || selected.length === 0) return true;
        const type = subtype == null || String(subtype).trim() === ""
            ? "unknown" : String(subtype).trim().toLowerCase();
        return selected.some(function (choice) {
            if (choice === "group:other") {
                return type !== "unknown" && !groupedTypes.has(type);
            }
            return String(choice).toLowerCase() === type ||
                homeTypeGroups[choice]?.some(member => member.toLowerCase() === type) || false;
        });
    };

    /**
     * Classify a pet policy from explicit MLS wording.
     * Missing, call-only, and contradictory policies require confirmation;
     * restriction text alone does not establish permission.
     * @param {*} raw Listing pet-policy text.
     * @returns {"allowed" | "prohibited" | "unknown"} Policy status.
     */
    filters.petPolicyStatus = function (raw) {
        const tokens = new Set(String(raw || "").toLowerCase().split(",").map(t => t.trim()));
        const allowed = ["yes", "cats ok", "dogs ok"].some(token => tokens.has(token));
        const prohibited = ["no", "none"].some(token => tokens.has(token));
        if (allowed && !prohibited) return "allowed";
        if (prohibited && !allowed) return "prohibited";
        return "unknown";
    };
}());
