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

        const wrap = strip.closest(WRAP);
        const root = wrap && wrap.querySelector(".dash-slider-root");
        const scale = root ? root.getBoundingClientRect() : rect;
        const ratio = Math.min(Math.max((clientX - scale.left) / scale.width, 0), 1);
        draw(strip, ratio, min + ratio * (max - min));
    }

    /**
     * Draw the cursor and readout at a fraction along the strip.
     *
     * @param {HTMLElement} strip - The `.dist` element.
     * @param {number} ratio - Position along the strip, 0 to 1.
     * @param {number} value - Value to show in the readout.
     * @returns {void}
     */
    function draw(strip, ratio, value) {
        const line = strip.querySelector(".dist__cursor");
        const readout = strip.querySelector(".dist__readout");
        if (!line || !readout) return;

        const pct = ratio * 100;
        line.style.left = pct + "%";
        readout.textContent = format(value, strip.dataset);

        readout.style.left = pct + "%";
        readout.style.transform =
            ratio < 0.12 ? "translateX(0)"
            : ratio > 0.88 ? "translateX(-100%)"
            : "translateX(-50%)";

        strip.classList.add("dist--hovered");
    }

    // Pointer events, not mouse events: the slider preventDefaults pointerdown
    // to stop text selection, which suppresses the compatibility mouse events,
    // so a mousemove listener sees nothing once a drag starts. The drag is
    // tracked explicitly because the slider takes pointer capture, after which
    // moves stop resolving to anything inside the strip.
    let draggingStrip = null;

    /**
     * Find the distribution strip belonging to an event target.
     *
     * @param {EventTarget} target - Element the event was dispatched to.
     * @returns {HTMLElement|null} The strip, or `null` when outside one.
     */
    function stripFor(target) {
        const wrap = target && target.closest ? target.closest(WRAP) : null;
        return wrap ? wrap.querySelector(".dist") : null;
    }

    /**
     * Say whether a pointer is over the control rather than the room below it.
     *
     * The wrap reserves a couple of rows under the marks that belong to the
     * layout, not to the slider, and a readout that appears down there is
     * pointing at nothing. The control ends where its labels do.
     *
     * @param {HTMLElement} strip - The `.dist` element.
     * @param {number} clientY - Pointer y position in viewport coordinates.
     * @returns {boolean} True when the pointer is on the graph, rail or marks.
     */
    function onControl(strip, clientY) {
        const wrap = strip.closest(WRAP);
        const root = wrap && wrap.querySelector(".dash-slider-root");
        if (!root) return true;
        return clientY >= strip.getBoundingClientRect().top
            && clientY <= root.getBoundingClientRect().bottom;
    }

    /**
     * Put the cursor on a handle's current rendered position.
     *
     * @param {HTMLElement} strip - The `.dist` element.
     * @returns {void}
     */
    function followHandle(strip) {
        const wrap = strip.closest(WRAP);
        const box = strip.getBoundingClientRect();
        const thumbs = wrap ? wrap.querySelectorAll(".dash-slider-thumb") : [];
        if (!box.width || !thumbs.length) return;

        let best = null;
        let bestGap = Infinity;
        thumbs.forEach(function (thumb) {
            const rect = thumb.getBoundingClientRect();
            const centre = rect.left + rect.width / 2;
            const gap = Math.abs(centre - lastPointerX);
            if (gap < bestGap) { bestGap = gap; best = { thumb: thumb, centre: centre }; }
        });

        const min = parseFloat(strip.dataset.min);
        const max = parseFloat(strip.dataset.max);
        const value = parseFloat(best.thumb.getAttribute("aria-valuenow"));
        const ratio = Math.min(Math.max((best.centre - box.left) / box.width, 0), 1);
        draw(strip, ratio, isFinite(value) ? value : min + ratio * (max - min));
    }

    // Watch the handle, not the pointer. The pointer event lands a frame ahead
    // of the React render that moves the handle, and an animation frame lands
    // a frame behind it. A mutation observer fires on the DOM write itself.
    const handleObserver = new MutationObserver(function () {
        if (draggingStrip) followHandle(draggingStrip);
    });

    let lastPointerX = 0;

    document.addEventListener("pointerdown", function (event) {
        const pressed = stripFor(event.target);
        draggingStrip = pressed && onControl(pressed, event.clientY) ? pressed : null;
        lastPointerX = event.clientX;
        if (!draggingStrip) return;
        followHandle(draggingStrip);
        const wrap = draggingStrip.closest(WRAP);
        if (wrap) {
            handleObserver.observe(wrap, {
                attributes: true,
                subtree: true,
                attributeFilter: ["style", "aria-valuenow"],
            });
        }
    }, true);

    document.addEventListener("pointermove", function (event) {
        lastPointerX = event.clientX;
        if (draggingStrip) return;
        const strip = stripFor(event.target);
        if (!strip) return;
        if (onControl(strip, event.clientY)) place(strip, event.clientX);
        else strip.classList.remove("dist--hovered");
    }, true);

    /**
     * Stop following the handle.
     *
     * @returns {void}
     */
    function endDrag() {
        draggingStrip = null;
        handleObserver.disconnect();
    }

    document.addEventListener("pointerup", endDrag, true);
    document.addEventListener("pointercancel", endDrag, true);

    document.addEventListener("pointerout", function (event) {
        if (draggingStrip) return;
        const wrap = event.target.closest ? event.target.closest(WRAP) : null;
        if (!wrap) return;
        if (wrap.contains(event.relatedTarget)) return;
        const strip = wrap.querySelector(".dist");
        if (strip) strip.classList.remove("dist--hovered");
    }, true);
})();
