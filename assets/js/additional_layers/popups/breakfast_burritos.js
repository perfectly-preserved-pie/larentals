(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupUtils = popupApi && popupApi.utils;
    const popupRuntime = popupApi && popupApi.runtime;
    const registerPopupBuilder = popupRuntime && popupRuntime.registerPopupBuilder;

    if (!popupUtils || typeof registerPopupBuilder !== "function") {
        console.error("Additional layer popup utils did not load before the breakfast burrito popup builder.");
        return;
    }

    const buildExternalLink = popupUtils.buildExternalLink;
    const escapeHtml = popupUtils.escapeHtml;
    const formatTextValue = popupUtils.formatTextValue;
    const getTrimmedString = popupUtils.getTrimmedString;
    const isBlankValue = popupUtils.isBlankValue;
    const renderPopupCard = popupUtils.renderPopupCard;

    /**
     * Build the address row value for a breakfast burrito popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {string} Escaped address or linked map destination.
     */
    function buildBreakfastBurritoAddress(properties) {
        const address = getTrimmedString(properties.address);
        const mapsUrl = getTrimmedString(properties.maps_url);

        if (!address) {
            return mapsUrl ? buildExternalLink(mapsUrl, "Open in Google Maps") : "N/A";
        }

        return mapsUrl ? buildExternalLink(mapsUrl, address) : escapeHtml(address);
    }

    /**
     * Build the rating row value for a breakfast burrito popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {string} Rating display string, or `N/A`.
     */
    function buildBreakfastBurritoRating(properties) {
        const rating = getTrimmedString(properties.rating);
        return rating ? `${escapeHtml(rating)} / 10` : "N/A";
    }

    /**
     * Build the photo row value for a breakfast burrito popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {string} HTML link to the photo, or `N/A`.
     */
    function buildBreakfastBurritoPhoto(properties) {
        return buildExternalLink(properties.picture_url, "View photo");
    }

    /**
     * Build the review/source row value for a breakfast burrito popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {string} HTML link to the best available review/source page, or `N/A`.
     */
    function buildBreakfastBurritoOriginalReview(properties) {
        if (!isBlankValue(properties.review_url)) {
            return buildExternalLink(properties.review_url, "Read on LABreakfastBurrito");
        }

        if (!isBlankValue(properties.source_url)) {
            return buildExternalLink(properties.source_url, "Browse LABreakfastBurrito");
        }

        if (!isBlankValue(properties.source_sheet_url)) {
            return buildExternalLink(properties.source_sheet_url, "Open rankings sheet");
        }

        return "N/A";
    }

    /**
     * Build the attribution source links for a breakfast burrito popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {string} Joined attribution links, or `N/A`.
     */
    function buildBreakfastBurritoSource(properties) {
        const links = [];

        if (!isBlankValue(properties.review_url)) {
            links.push(buildExternalLink(properties.review_url, "Original review"));
        }

        if (!isBlankValue(properties.source_url)) {
            links.push(buildExternalLink(properties.source_url, "LABreakfastBurrito"));
        }

        if (!isBlankValue(properties.source_sheet_url)) {
            links.push(buildExternalLink(properties.source_sheet_url, "Rankings sheet"));
        }

        return links.length > 0 ? links.join(" | ") : "N/A";
    }

    /**
     * Build the attribution banner displayed above breakfast burrito popup rows.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {string} HTML banner, or an empty string when no attribution links exist.
     */
    function buildBreakfastBurritoAttribution(properties) {
        const sourceLinks = buildBreakfastBurritoSource(properties);
        if (sourceLinks === "N/A") {
            return "";
        }

        return `
            <div class="additional-layer-popup__attribution">
                <div class="additional-layer-popup__attribution-title">Source Attribution</div>
                <div>
                    Breakfast burrito rankings and review content are sourced from LABreakfastBurrito.
                </div>
                <div class="additional-layer-popup__attribution-links">
                    ${sourceLinks}
                </div>
            </div>
        `;
    }

    /**
     * Build the detail rows rendered inside a breakfast burrito popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {{ label: string, value: string }[]} Popup rows for the feature.
     */
    function buildBreakfastBurritoRows(properties) {
        return [
            {
                label: "Status",
                value: formatTextValue(properties.review_status),
            },
            {
                label: "Rating",
                value: buildBreakfastBurritoRating(properties),
            },
            {
                label: "Neighborhood",
                value: formatTextValue(properties.neighborhood),
            },
            {
                label: "Price",
                value: formatTextValue(properties.price),
            },
            {
                label: "Size",
                value: formatTextValue(properties.size),
            },
            {
                label: "Value",
                value: formatTextValue(properties.value_rating),
            },
            {
                label: "Address",
                value: buildBreakfastBurritoAddress(properties),
            },
            {
                label: "What's Inside",
                value: formatTextValue(properties.whats_inside),
            },
            {
                label: "Photo",
                value: buildBreakfastBurritoPhoto(properties),
            },
            {
                label: isBlankValue(properties.review_url) ? "Source" : "Original Review",
                value: buildBreakfastBurritoOriginalReview(properties),
            },
        ];
    }

    /**
     * Build the complete breakfast burrito popup markup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the breakfast burrito entry.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildBreakfastBurritoPopupContent(properties) {
        const title = getTrimmedString(properties.name) || "Breakfast Burrito";

        return renderPopupCard({
            title: title,
            rows: buildBreakfastBurritoRows(properties),
            banner: buildBreakfastBurritoAttribution(properties),
            sizeVariant: "wide",
            heightVariant: "tall",
        });
    }

    registerPopupBuilder("buildBreakfastBurritoPopupContent", buildBreakfastBurritoPopupContent);
})();
