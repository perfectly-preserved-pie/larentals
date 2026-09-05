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
     * Build a row from a supercluster leaf.
     *
     * A cluster bubble hides its listings, but the panel should still name them,
     * so each visible cluster is expanded through the supercluster index. Leaves
     * have no rendered marker, hence the coordinates for the click handler.
     *
     * @param {object} leaf GeoJSON feature from `getLeaves`.
     * @param {Element} clusterEl Bubble the leaf is currently hidden inside.
     * @returns {object|null} Row descriptor, or `null` for an unusable leaf.
     */
    function rowFromLeaf(leaf, clusterEl) {
        var props = leaf && leaf.properties;
        var coords = leaf && leaf.geometry && leaf.geometry.coordinates;
        if (!props || !coords) return null;
        return {
            el: null,
            clusterEl: clusterEl || null,
            props: props,
            latlng: [coords[1], coords[0]],
            price: Number(props.list_price),
            mls: props.mls_number,
            address: props.full_street_address,
            beds: props.bedrooms,
            baths: props.total_bathrooms,
            sqft: props.sqft,
            subtype: props.subtype,
            ppsqft: Number(props.ppsqft),
            listed: props.listed_date,
        };
    }

    /**
     * Count every listing inside the viewport, clustered ones included.
     *
     * A cluster bubble stands for many listings, so the headline count adds its
     * size rather than counting the bubble as one. Its on-screen label is
     * abbreviated ("3k"), hence the exact size travelling as a data attribute.
     *
     * @param {DOMRect} box The map viewport rectangle.
     * @returns {number} Listings visible in frame.
     */
    function countInView(box) {
        var total = 0;

        var clusters = document.querySelectorAll("[data-cluster-count]");
        for (var c = 0; c < clusters.length; c += 1) {
            if (!inside(clusters[c], box)) continue;
            var size = Number(clusters[c].getAttribute("data-cluster-count"));
            if (isFinite(size)) total += size;
        }

        var pins = document.querySelectorAll(".price-marker[data-mls]");
        for (var i = 0; i < pins.length; i += 1) {
            if (inside(pins[i], box)) total += 1;
        }
        return total;
    }

    /**
     * Report whether an element's centre sits inside a rectangle.
     *
     * @param {Element} el Element to test.
     * @param {DOMRect} box Rectangle to test against.
     * @returns {boolean} True when the element's centre is inside.
     */
    function inside(el, box) {
        var rect = el.getBoundingClientRect();
        if (!rect.width && !rect.height) return false;
        var x = rect.left + rect.width / 2;
        var y = rect.top + rect.height / 2;
        return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
    }

    /**
     * Update the headline count to describe what is in frame.
     *
     * @param {number} total Listings visible in frame.
     * @returns {void}
     */
    function updateMatchCount(total) {
        var badge = document.querySelector(".match-count");
        if (!badge) return;
        var path = String(window.location.pathname || "").toLowerCase();
        var noun = path.indexOf("/buy") === 0 ? "homes" : "rentals";
        badge.textContent = total
            ? total.toLocaleString("en-US") + " " + noun + " in view"
            : "No " + noun + " in view";
    }

    /**
     * Read the selected sort order.
     *
     * @returns {string} Sort key, defaulting to cheapest first.
     */
    function currentSort() {
        var select = document.querySelector("[data-results-sort]");
        return select && select.value ? select.value : "price-asc";
    }

    /**
     * Order two rows by a numeric field, always sinking missing values.
     *
     * A listing with no square footage should not win "largest first", so blanks
     * go last whichever direction is chosen.
     *
     * @param {string} field Row property to compare.
     * @param {number} direction 1 for ascending, -1 for descending.
     * @returns {function(object, object): number} Comparator.
     */
    function byNumber(field, direction) {
        return function (a, b) {
            var left = Number(a[field]);
            var right = Number(b[field]);
            var leftOk = isFinite(left);
            var rightOk = isFinite(right);
            if (!leftOk && !rightOk) return 0;
            if (!leftOk) return 1;
            if (!rightOk) return -1;
            return (left - right) * direction;
        };
    }

    /**
     * Build the comparator for a sort key.
     *
     * @param {string} key Sort key from the select.
     * @returns {function(object, object): number} Comparator.
     */
    function comparatorFor(key) {
        switch (key) {
            case "price-desc": return byNumber("price", -1);
            case "beds-desc": return byNumber("beds", -1);
            case "sqft-desc": return byNumber("sqft", -1);
            case "ppsqft-asc": return byNumber("ppsqft", 1);
            case "newest": return function (a, b) {
                var left = Date.parse(a.listed);
                var right = Date.parse(b.listed);
                if (isNaN(left) && isNaN(right)) return 0;
                if (isNaN(left)) return 1;
                if (isNaN(right)) return -1;
                return right - left;
            };
            default: return byNumber("price", 1);
        }
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

        var index = (window.larentals || {}).clusterIndex;
        var clusters = document.querySelectorAll("[data-cluster-id]");
        for (var c = 0; c < clusters.length; c += 1) {
            if (!index || !inside(clusters[c], box)) continue;
            var clusterId = Number(clusters[c].getAttribute("data-cluster-id"));
            if (!isFinite(clusterId)) continue;
            var leaves = [];
            try {
                leaves = index.getLeaves(clusterId, Infinity);
            } catch (error) {
                leaves = [];
            }
            for (var k = 0; k < leaves.length; k += 1) {
                var leafRow = rowFromLeaf(leaves[k], clusters[c]);
                if (leafRow) rows.push(leafRow);
            }
        }

        var markers = document.querySelectorAll(".price-marker[data-mls]");
        for (var i = 0; i < markers.length; i += 1) {
            var el = markers[i];
            if (!inside(el, box)) continue;
            rows.push({
                el: el,
                price: Number(el.getAttribute("data-price")),
                mls: el.getAttribute("data-mls"),
                address: el.getAttribute("data-address"),
                beds: el.getAttribute("data-beds"),
                baths: el.getAttribute("data-baths"),
                sqft: el.getAttribute("data-sqft"),
                subtype: el.getAttribute("data-subtype"),
                ppsqft: Number(el.getAttribute("data-ppsqft")),
                listed: el.getAttribute("data-listed"),
            });
        }

        rows.sort(comparatorFor(currentSort()));
        return {
            rows: rows,
            clustered: document.querySelectorAll(".marker-cluster").length > 0,
            inView: countInView(box),
        };
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

    /**
     * Point the map at whichever row the cursor is on.
     *
     * A row backed by a rendered pin highlights that pin. A row still inside a
     * cluster highlights the bubble hiding it, which is the only thing on screen
     * that represents it.
     *
     * @param {object} entry Row descriptor.
     * @param {boolean} on Whether to turn the highlight on.
     * @returns {void}
     */
    function highlight(entry, on) {
        if (!entry) return;
        var el = entry.el || entry.clusterEl;
        if (!el) return;
        var icon = el.closest(".leaflet-marker-icon") || el;
        icon.classList.toggle("is-highlighted", !!on);
    }

    /**
     * Clear every highlight, so a re-render cannot strand one.
     *
     * @returns {void}
     */
    function clearHighlights() {
        var lit = document.querySelectorAll(".leaflet-marker-icon.is-highlighted");
        for (var i = 0; i < lit.length; i += 1) lit[i].classList.remove("is-highlighted");
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

        clearHighlights();
        var result = collectVisible();
        currentRows = result.rows.slice(0, MAX_ROWS);
        updateMatchCount(result.inView);

        var scale = (window.larentals || {}).priceScale;
        if (scale) {
            scale.update(result.rows.map(function (row) { return row.price; }));
            scale.repaint();
        }

        if (!currentRows.length) {
            list.innerHTML = '<p class="results-panel__empty">No listings in view. Pan or zoom the map.</p>';
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

    document.addEventListener("mouseover", function (event) {
        var row = event.target && event.target.closest ? event.target.closest(".results-row") : null;
        if (!row) return;
        clearHighlights();
        highlight(currentRows[Number(row.getAttribute("data-results-index"))], true);
    });

    document.addEventListener("mouseout", function (event) {
        var row = event.target && event.target.closest ? event.target.closest(".results-row") : null;
        if (!row) return;
        highlight(currentRows[Number(row.getAttribute("data-results-index"))], false);
    });

    document.addEventListener("change", function (event) {
        if (event.target && event.target.matches && event.target.matches("[data-results-sort]")) {
            refresh();
        }
    });

    document.addEventListener("click", function (event) {
        var row = event.target && event.target.closest ? event.target.closest(".results-row") : null;
        if (!row) return;
        var entry = currentRows[Number(row.getAttribute("data-results-index"))];
        if (!entry) return;
        if (entry.el) {
            var target = entry.el.closest(".leaflet-marker-icon") || entry.el;
            target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
            return;
        }
        var popups = (window.larentals || {}).popups;
        if (popups && entry.latlng) popups.openAt(entry.latlng, entry.props || {});
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
