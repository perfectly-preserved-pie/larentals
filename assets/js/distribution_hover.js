(function () {
    "use strict";

    const WRAP = ".range-filter__hybrid-slider-wrap, .range-filter__slider-with-switch";

    /**
     * Format a value for the readout using the strip's own prefix and suffix.
     *
     * @param {number} value - Value at the hovered position.
     * @param {DOMStringMap} data - Dataset from the strip element.
     * @returns {string} The formatted label.
     */
    function format(value, data) {
        const rounded = Math.round(value);
        const grouped = rounded.toLocaleString("en-US");
        return (data.prefix || "") + grouped + (data.suffix || "");
    }

    /**
     * Position the cursor line and readout for a pointer event.
     *
     * @param {HTMLElement} strip - The `.dist` element being hovered.
     * @param {number} clientX - Pointer x position in viewport coordinates.
     * @returns {void}
     */
    function place(strip, clientX) {
        const rect = strip.getBoundingClientRect();
        if (rect.width <= 0) return;

        const min = parseFloat(strip.dataset.min);
        const max = parseFloat(strip.dataset.max);
        if (!isFinite(min) || !isFinite(max) || max <= min) return;

        const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
        const line = strip.querySelector(".dist__cursor");
        const readout = strip.querySelector(".dist__readout");
        if (!line || !readout) return;

        const pct = ratio * 100;
        line.style.left = pct + "%";
        readout.textContent = format(min + ratio * (max - min), strip.dataset);

        readout.style.left = pct + "%";
        readout.style.transform =
            ratio < 0.12 ? "translateX(0)"
            : ratio > 0.88 ? "translateX(-100%)"
            : "translateX(-50%)";

        strip.classList.add("dist--hovered");
    }

    document.addEventListener("mousemove", function (event) {
        const wrap = event.target.closest ? event.target.closest(WRAP) : null;
        if (!wrap) return;
        const strip = wrap.querySelector(".dist");
        if (strip) place(strip, event.clientX);
    }, true);

    document.addEventListener("mouseout", function (event) {
        const wrap = event.target.closest ? event.target.closest(WRAP) : null;
        if (!wrap) return;
        if (wrap.contains(event.relatedTarget)) return;
        const strip = wrap.querySelector(".dist");
        if (strip) strip.classList.remove("dist--hovered");
    }, true);
})();
