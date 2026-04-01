window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
        /**
         * Apply the exact commute verification result to the current prefiltered listings.
         *
         * @param {Object} prefilteredGeojson Current FeatureCollection after clientside filters.
         * @param {Object} commuteRequest Normalized commute request metadata from the server.
         * @param {Object} exactResult Exact route-check result metadata for the current candidate set.
         * @param {string} displayMode Selected map display mode for partial verification.
         * @returns {Object} Final map GeoJSON after exact commute verification.
         */
        applyExactCommuteFilter: function(prefilteredGeojson, commuteRequest, exactResult, displayMode) {
            if (!prefilteredGeojson || !Array.isArray(prefilteredGeojson.features)) {
                return window.dash_clientside.no_update;
            }

            if (!commuteRequest?.requested) {
                return prefilteredGeojson;
            }

            if (!commuteRequest?.active) {
                return emptyFeatureCollection();
            }

            const currentSignature = buildCommuteCandidateSignature(
                commuteRequest.signature,
                prefilteredGeojson,
            );

            if (!currentSignature) {
                return prefilteredGeojson;
            }

            if (exactResult?.signature !== currentSignature) {
                return prefilteredGeojson;
            }

            if (exactResult?.error) {
                return {
                    type: "FeatureCollection",
                    features: prefilteredGeojson.features.map((feature) => (
                        cloneFeatureWithCommuteState(
                            feature,
                            "rough_match",
                            "Rough commute match only",
                        )
                    )),
                };
            }

            const verifiedSet = normalizeListingIdSet(exactResult?.eligible_mls);
            const roughSet = normalizeListingIdSet(exactResult?.rough_mls);
            const includeRough = displayMode === "include_rough";
            const filteredFeatures = prefilteredGeojson.features
                .filter((feature) => {
                    const listingId = normalizeListingId(feature?.properties?.mls_number);
                    if (!listingId) return false;
                    if (verifiedSet.has(listingId)) return true;
                    return includeRough && roughSet.has(listingId);
                })
                .map((feature) => {
                    const listingId = normalizeListingId(feature?.properties?.mls_number);
                    const matchState = verifiedSet.has(listingId)
                        ? "verified_match"
                        : "rough_match";
                    const statusText = matchState === "verified_match"
                        ? "Verified commute match"
                        : "Rough commute match only";
                    return cloneFeatureWithCommuteState(feature, matchState, statusText);
                })
                .sort((a, b) => (
                    commuteStateSortRank(a?.properties?.commute_match_state)
                    - commuteStateSortRank(b?.properties?.commute_match_state)
                ));

            return {
                type: "FeatureCollection",
                features: filteredFeatures,
            };
        }
    })
});
