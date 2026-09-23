(function () {
    "use strict";

    var root = window.larentals = window.larentals || {};

    // Five vivid, perceptually ordered bands read clearly on individual markers.
    var PRICE_BANDS = ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"];

    var MISSING_COLOR = "#6b7280";

    var MIN_SAMPLE = 5;

    var FALLBACK = {
        lease: { low: 1950, high: 4000 },
        buy: { low: 449000, high: 949000 },
    };

    var sorted = [];

    /**
     * Read the price anchors for the page being viewed.
     * The fallback scale changes with the buy or lease page when there are too few
     * visible prices to rank.
     *
     * @returns {{low: number, high: number}} Fallback anchors.
     */
    function fallbackAnchors() {
        var path = String(window.location.pathname || "").toLowerCase();
        return path.indexOf("/buy") === 0 ? FALLBACK.buy : FALLBACK.lease;
    }

    /**
     * Turn a rank fraction into a colour.
     * Clamp out-of-range fractions so marker styling stays stable at the ends of
     * the scale.
     *
     * @param {number} fraction Position in the visible range, 0 to 1.
     * @returns {string} One of the ordered price-band colors.
     */
    function colorForFraction(fraction) {
        var t = Math.max(0, Math.min(1, fraction));
        var band = Math.min(PRICE_BANDS.length - 1, Math.floor(t * PRICE_BANDS.length));
        return PRICE_BANDS[band];
    }

    function relativeLuminance(color) {
        var hex = String(color).replace("#", "");
        if (hex.length === 3) hex = hex.split("").map(function (digit) { return digit + digit; }).join("");
        var channels = [0, 2, 4].map(function (offset) {
            var value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
            return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    }

    /**
     * Report what share of the visible listings cost less than a price.
     * Equal prices share a rank, so two identical listings are never painted
     * different colours.
     *
     * @param {number} price Listing price.
     * @returns {number} Fraction of visible listings that are cheaper, 0 to 1.
     */
    function rankFraction(price) {
        var low = 0;
        var high = sorted.length;
        while (low < high) {
            var mid = (low + high) >> 1;
            if (sorted[mid] < price) low = mid + 1;
            else high = mid;
        }
        return sorted.length > 1 ? low / (sorted.length - 1) : 0;
    }

    var scale = root.priceScale = root.priceScale || {};

    /**
     * Replace the sample the ranking is measured against.
     * A handful of listings makes percentile colors jump around, so small samples
     * use page-specific price anchors instead.
     *
     * @param {number[]} prices Prices of every listing currently in view.
     * @returns {void}
     */
    scale.update = function (prices) {
        var usable = [];
        for (var i = 0; i < (prices || []).length; i += 1) {
            var price = Number(prices[i]);
            if (isFinite(price)) usable.push(price);
        }
        usable.sort(function (a, b) { return a - b; });
        sorted = usable.length >= MIN_SAMPLE ? usable : [];
    };

    /**
     * Find one listing's position on the price scale.
     * Use a visible-listing percentile when the sample is large enough; otherwise
     * use the page's fixed anchors.
     *
     * @param {number} price Listing price.
     * @returns {number|null} Scale fraction, or null for an invalid price.
     */
    scale.fractionFor = function (price) {
        var value = Number(price);
        if (!isFinite(value)) return null;
        if (sorted.length) return rankFraction(value);
        var anchors = fallbackAnchors();
        var span = anchors.high - anchors.low;
        return span > 0 ? Math.max(0, Math.min(1, (value - anchors.low) / span)) : 0.5;
    };

    scale.colorFor = function (price) {
        var fraction = scale.fractionFor(price);
        return fraction === null ? MISSING_COLOR : colorForFraction(fraction);
    };

    scale.labelColorFor = function (price) {
        var fraction = scale.fractionFor(price);
        if (fraction === null) return "#ffffff";
        var background = colorForFraction(fraction);
        return relativeLuminance(background) > 0.179 ? "#172033" : "#ffffff";
    };

    /**
     * Repaint every rendered pin for the current sample.
     * Writes only where the colour actually changed. The results panel watches
     * the marker pane for style mutations to know when to redraw, and repainting
     * unconditionally would keep waking it with its own work.
     *
     * @returns {void}
     */
    scale.repaint = function () {
        var pins = document.querySelectorAll(".price-marker[data-price]");
        for (var i = 0; i < pins.length; i += 1) {
            var pin = pins[i];
            var raw = pin.getAttribute("data-price");
            if (raw === null || raw === "") continue;
            var color = scale.colorFor(Number(raw));
            if (pin.dataset.priceColor === color) continue;
            pin.style.background = color;
            pin.style.color = scale.labelColorFor(raw);
            pin.dataset.priceColor = color;
        }
        var clusters = document.querySelectorAll("[data-cluster-price]");
        for (var c = 0; c < clusters.length; c += 1) {
            var cluster = clusters[c];
            var rawClusterPrice = cluster.getAttribute("data-cluster-price");
            if (rawClusterPrice === null || rawClusterPrice === "") continue;
            var clusterPrice = Number(rawClusterPrice);
            if (!isFinite(clusterPrice)) continue;
            var clusterColor = scale.colorFor(clusterPrice);
            var colorLayers = cluster.querySelectorAll(".cluster-price-core, .cluster-price-ring");
            for (var layerIndex = 0; layerIndex < colorLayers.length; layerIndex += 1) {
                var colorLayer = colorLayers[layerIndex];
                if (colorLayer.dataset.priceColor !== clusterColor) {
                    colorLayer.style.backgroundColor = clusterColor;
                    colorLayer.dataset.priceColor = clusterColor;
                }
            }
            var core = cluster.querySelector(".cluster-price-core");
            if (core) core.style.color = scale.labelColorFor(clusterPrice);
        }
    };
})();
