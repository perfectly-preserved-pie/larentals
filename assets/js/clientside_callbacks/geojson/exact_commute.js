window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
        requestExactCommuteRefresh: function(prefilteredGeojson, commuteRequest) {
            if (!Array.isArray(prefilteredGeojson?.features)) {
                return window.dash_clientside.no_update;
            }

            if (!commuteRequest?.requested || !commuteRequest?.active || !commuteRequest?.signature) {
                return window.dash_clientside.no_update;
            }

            return {
                commute_signature: commuteRequest.signature,
                candidate_signature: buildCommuteCandidateSignature(
                    commuteRequest.signature,
                    prefilteredGeojson,
                ),
                refreshed_at: Date.now(),
            };
        },
        buildVerifiedBoundaryFromFeatures: function(featureCollection) {
            const features = Array.isArray(featureCollection?.features)
                ? featureCollection.features
                : [];
            const pointFeatures = features
                .map((feature) => {
                    const coords = feature?.geometry?.coordinates;
                    if (!Array.isArray(coords) || coords.length < 2) {
                        return null;
                    }
                    return turf.point([coords[0], coords[1]]);
                })
                .filter(Boolean);

            if (!pointFeatures.length) {
                return emptyFeatureCollection();
            }

            if (pointFeatures.length === 1) {
                const circle = turf.circle(pointFeatures[0].geometry.coordinates, 0.2, {units: "miles"});
                return {type: "FeatureCollection", features: [circle]};
            }

            if (pointFeatures.length === 2) {
                const line = turf.lineString(pointFeatures.map((feature) => feature.geometry.coordinates));
                const bufferedLine = turf.buffer(line, 0.2, {units: "miles"});
                return {
                    type: "FeatureCollection",
                    features: bufferedLine ? [bufferedLine] : [],
                };
            }

            const collection = turf.featureCollection(pointFeatures);
            const convexHull = turf.convex(collection);
            if (convexHull) {
                return {type: "FeatureCollection", features: [convexHull]};
            }

            const bboxPolygon = turf.bboxPolygon(turf.bbox(collection));
            return {type: "FeatureCollection", features: bboxPolygon ? [bboxPolygon] : []};
        },
        clearActiveConvexHull: function() {
            const runtime = window.larentals;
            const polygonLayer = runtime?.currentConvexHull;
            const hullMap = runtime?.currentConvexHullMap || polygonLayer?._map;
            if (!polygonLayer || !hullMap || typeof hullMap.removeLayer !== "function") {
                if (runtime) {
                    runtime.currentConvexHull = null;
                    runtime.currentConvexHullMap = null;
                }
                return;
            }

            try {
                hullMap.removeLayer(polygonLayer);
            } catch (error) {
                console.warn("Failed to clear stale commute hull.", error);
            }

            runtime.currentConvexHull = null;
            runtime.currentConvexHullMap = null;
        },
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

            window.dash_clientside.clientside.clearActiveConvexHull();

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
                            "Estimated commute match",
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
                        : "Estimated commute match";
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
        },
        deriveDisplayedCommuteBoundary: function(
            coarseBoundaryGeojson,
            visibleListingsGeojson,
            commuteRequest,
            exactResult,
            displayMode,
        ) {
            const coarseBoundary = (
                coarseBoundaryGeojson
                && Array.isArray(coarseBoundaryGeojson.features)
            )
                ? coarseBoundaryGeojson
                : emptyFeatureCollection();

            if (!commuteRequest?.requested) {
                return coarseBoundary;
            }

            if (!commuteRequest?.active) {
                return emptyFeatureCollection();
            }

            if (displayMode === "include_rough") {
                return coarseBoundary;
            }

            const hasVerifiedSubset = Boolean(
                exactResult
                && !exactResult.error
                && Number(exactResult.checked_candidates || 0) > 0
                && Number(exactResult.matched_candidates || 0) > 0
            );

            if (!hasVerifiedSubset) {
                return coarseBoundary;
            }

            return window.dash_clientside.clientside.buildVerifiedBoundaryFromFeatures(
                visibleListingsGeojson,
            );
        }
    })
});
