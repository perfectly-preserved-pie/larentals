// Results panel: the listings currently visible on the map.
//
// Reads the rendered marker elements rather than the Leaflet map object, since
// dash-leaflet never exposes the map instance and the markers are plain DOM
// carrying their own listing data. "What is on screen" is a rectangle
// intersection, and the panel and the pins cannot disagree about it.

(function () {
    "use strict";

    var MAX_ROWS = 150;
    var refreshTimer = null;

    /**
     * Escape text for safe HTML interpolation.
     *
     * @param {unknown} value Raw text value.
     * @returns {string} Escaped string.
     */
    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    /**
     * Convert a value to a trimmed string, or null when it says nothing.
     *
     * @param {unknown} value Raw value.
     * @returns {string|null} Cleaned string or `null`.
     */
    function clean(value) {
        if (value === null || value === undefined) return null;
        var text = String(value).trim();
        if (!text || ["none", "null", "nan", "unknown"].indexOf(text.toLowerCase()) !== -1) {
            return null;
        }
        return text;
    }

    /**
     * Format a price for a list row.
     *
     * @param {unknown} value Raw list price.
     * @returns {string} Display price.
     */
    function formatPrice(value) {
        var n = Number(value);
        if (!isFinite(n)) return "n/a";
        return "$" + Math.round(n).toLocaleString("en-US");
    }

    /**
     * Collect the price markers whose centre falls inside the map viewport.
     *
     * @returns {{rows: object[], clustered: boolean}} Visible rows, and whether
     *   cluster bubbles are covering the view.
     */
    function collectVisible() {
        var container = document.querySelector(".leaflet-container");
        if (!container) return { rows: [], clustered: false };
        var box = container.getBoundingClientRect();
        var rows = [];

        var markers = document.querySelectorAll(".price-marker[data-mls]");
        for (var i = 0; i < markers.length; i += 1) {
            var el = markers[i];
            var rect = el.getBoundingClientRect();
            if (!rect.width && !rect.height) continue;
            var x = rect.left + rect.width / 2;
            var y = rect.top + rect.height / 2;
            if (x < box.left || x > box.right || y < box.top || y > box.bottom) continue;
            rows.push({
                el: el,
                price: Number(el.getAttribute("data-price")),
                mls: el.getAttribute("data-mls"),
                address: el.getAttribute("data-address"),
                beds: el.getAttribute("data-beds"),
                baths: el.getAttribute("data-baths"),
                sqft: el.getAttribute("data-sqft"),
                subtype: el.getAttribute("data-subtype"),
            });
        }

        // Cheapest first. The panel exists to make price scannable, and that is
        // the order someone shopping on price reads in.
        rows.sort(function (a, b) {
            if (!isFinite(a.price)) return 1;
            if (!isFinite(b.price)) return -1;
            return a.price - b.price;
        });

        return { rows: rows, clustered: document.querySelectorAll(".marker-cluster").length > 0 };
    }

    /**
     * Render one listing row.
     *
     * @param {object} row Row descriptor from `collectVisible`.
     * @param {number} index Row position, used to reconnect the click handler.
     * @returns {string} HTML for the row.
     */
    function renderRow(row, index) {
        var address = clean(row.address) || "Unknown address";
        var beds = clean(row.beds);
        var baths = clean(row.baths);
        var sqft = Number(row.sqft);
        var subtype = clean(row.subtype);
        var meta = [];
        if (beds || baths) meta.push((beds || "?") + " bd / " + (baths || "?") + " ba");
        if (isFinite(sqft) && sqft > 0) meta.push(sqft.toLocaleString("en-US") + " sq ft");
        if (subtype) meta.push(subtype);

        return (
            '<button type="button" class="results-row" data-results-index="' + index + '">' +
            '<span class="results-row__price">' + escapeHtml(formatPrice(row.price)) + "</span>" +
            '<span class="results-row__address">' + escapeHtml(address) + "</span>" +
            '<span class="results-row__meta">' + escapeHtml(meta.join(" · ")) + "</span>" +
            "</button>"
        );
    }

    var currentRows = [];

    /**
     * Redraw the panel for the current viewport.
     *
     * @returns {void}
     */
    function refresh() {
        var list = document.querySelector(".results-panel__list");
        var count = document.querySelector(".results-panel__count");
        if (!list) return;

        var result = collectVisible();
        currentRows = result.rows.slice(0, MAX_ROWS);

        if (!currentRows.length) {
            list.innerHTML = result.clustered
                ? '<p class="results-panel__empty">Zoom in to list the listings behind these clusters.</p>'
                : '<p class="results-panel__empty">No listings in view. Pan or zoom the map.</p>';
            if (count) count.textContent = "";
            return;
        }

        list.innerHTML = currentRows.map(renderRow).join("");
        if (count) {
            count.textContent = result.rows.length > MAX_ROWS
                ? MAX_ROWS + " of " + result.rows.length.toLocaleString("en-US")
                : String(result.rows.length);
        }
    }

    /**
     * Queue a redraw, collapsing bursts of map events into one.
     *
     * @returns {void}
     */
    function scheduleRefresh() {
        window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(refresh, 150);
    }

    document.addEventListener("click", function (event) {
        var row = event.target && event.target.closest ? event.target.closest(".results-row") : null;
        if (!row) return;
        var entry = currentRows[Number(row.getAttribute("data-results-index"))];
        if (!entry || !entry.el) return;
        var target = entry.el.closest(".leaflet-marker-icon") || entry.el;
        target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    });

    document.addEventListener("click", function (event) {
        var toggle = event.target && event.target.closest
            ? event.target.closest("[data-column-toggle]")
            : null;
        if (!toggle) return;
        var layout = document.querySelector(".listing-page-layout");
        if (!layout) return;
        var hidden = layout.classList.toggle(
            toggle.getAttribute("data-column-toggle") === "results"
                ? "is-results-hidden"
                : "is-filters-hidden"
        );
        toggle.setAttribute("aria-expanded", hidden ? "false" : "true");
        window.setTimeout(function () {
            window.dispatchEvent(new Event("resize"));
            scheduleRefresh();
        }, 240);
    });

    var observer = new MutationObserver(scheduleRefresh);
    var observing = false;

    /**
     * Start observing the Leaflet marker pane once it exists.
     *
     * @returns {void}
     */
    function bind() {
        if (observing) return;
        var pane = document.querySelector(".leaflet-marker-pane");
        if (!pane) return;
        observer.observe(pane, { childList: true, subtree: true, attributes: true, attributeFilter: ["style"] });
        observing = true;
        refresh();
    }

    window.setInterval(bind, 700);
    document.addEventListener("DOMContentLoaded", bind);
})();
