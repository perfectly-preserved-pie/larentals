window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
        /**
         * Apply the exact commute verification result to the current prefiltered listings.
         *
         * @param {Object} prefilteredGeojson Current FeatureCollection after clientside filters.
         * @param {Object} commuteRequest Normalized commute request metadata from the server.
         * @param {Object} exactResult Exact route-check result metadata for the current candidate set.
         * @returns {Object} Final map GeoJSON after exact commute verification.
         */
        applyExactCommuteFilter: function(prefilteredGeojson, commuteRequest, exactResult) {
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
                return prefilteredGeojson;
            }

            return filterFeatureCollectionByListingIds(
                prefilteredGeojson,
                exactResult?.eligible_mls,
            );
        }
    })
});
