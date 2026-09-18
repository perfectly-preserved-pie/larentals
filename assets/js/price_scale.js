(function () {
    "use strict";

    var root = window.larentals = window.larentals || {};

    var BANDS = [
        { upTo: 0.4, h: [200, 207], s: [70, 72], l: [46, 40] },
        { upTo: 0.8, h: [207, 216], s: [72, 76], l: [40, 31] },
        { upTo: 1.0, h: [216, 226], s: [76, 82], l: [31, 21] },
    ];

    var MISSING_COLOR = "#6b7280";

    var MIN_SAMPLE = 5;

    var FALLBACK = {
        lease: { low: 1950, high: 4000 },
        buy: { low: 449000, high: 949000 },
    };

    var sorted = [];

    /**
     * Read the price anchors for the page being viewed.
     *
     * @returns {{low: number, high: number}} Fallback anchors.
     */
    function fallbackAnchors() {
        var path = String(window.location.pathname || "").toLowerCase();
        return path.indexOf("/buy") === 0 ? FALLBACK.buy : FALLBACK.lease;
    }

    /**
     * Turn a rank fraction into a colour.
     *
     * @param {number} fraction Position in the visible range, 0 to 1.
     * @returns {string} An `hsl(...)` colour.
     */
    function colorForFraction(fraction) {
        var t = Math.max(0, Math.min(1, fraction));
        var start = 0;
        for (var i = 0; i < BANDS.length; i += 1) {
            var band = BANDS[i];
            if (t <= band.upTo || i === BANDS.length - 1) {
                var span = band.upTo - start;
                var within = Math.max(0, Math.min(1, span > 0 ? (t - start) / span : 0));
                var at = function (pair) {
                    return pair[0] + within * (pair[1] - pair[0]);
                };
                return "hsl(" + at(band.h).toFixed(0) + ", "
                    + at(band.s).toFixed(0) + "%, " + at(band.l).toFixed(0) + "%)";
            }
            start = band.upTo;
        }
        return MISSING_COLOR;
    }

    /**
     * Report what share of the visible listings cost less than a price.
     *
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
     * Colour one listing.
     *
     * @param {number} price Listing price.
     * @returns {string} A CSS colour.
     */
    scale.colorFor = function (price) {
        var value = Number(price);
        if (!isFinite(value)) return MISSING_COLOR;
        if (sorted.length) return colorForFraction(rankFraction(value));

        var anchors = fallbackAnchors();
        var span = anchors.high - anchors.low;
        return colorForFraction(span > 0 ? (value - anchors.low) / span : 0.5);
    };

    /**
     * Repaint every rendered pin for the current sample.
     *
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
            pin.dataset.priceColor = color;
        }
    };
})();
