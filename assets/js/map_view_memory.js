// Remember where the map was left, in localStorage, per page. Rent and For
// sale keep separate positions since they are separate searches.

(function () {
    "use strict";

    var SAVE_DELAY_MS = 400;
    var saveTimer = null;
    var restored = false;

    /**
     * Storage key for the current page.
     *
     * @returns {string} Key scoped to the listing page being viewed.
     */
    function storageKey() {
        var path = String(window.location.pathname || "").toLowerCase();
        return "larentals:map-view:" + (path.indexOf("/buy") === 0 ? "buy" : "lease");
    }

    /**
     * Read the remembered view.
     *
     * Storage can throw in private windows and can hold anything, so a bad or
     * missing value has to look the same as no memory at all.
     *
     * @returns {{lat: number, lng: number, zoom: number}|null} Saved view.
     */
    function readSaved() {
        try {
            var raw = window.localStorage.getItem(storageKey());
            if (!raw) return null;
            var parsed = JSON.parse(raw);
            if (!parsed) return null;
            var lat = Number(parsed.lat);
            var lng = Number(parsed.lng);
            var zoom = Number(parsed.zoom);
            if (!isFinite(lat) || !isFinite(lng) || !isFinite(zoom)) return null;
            if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
            return { lat: lat, lng: lng, zoom: zoom };
        } catch (error) {
            return null;
        }
    }

    /**
     * Store the map's current centre and zoom.
     *
     * @param {object} map The Leaflet map.
     * @returns {void}
     */
    function save(map) {
        try {
            var centre = map.getCenter();
            window.localStorage.setItem(storageKey(), JSON.stringify({
                lat: centre.lat,
                lng: centre.lng,
                zoom: map.getZoom(),
            }));
        } catch (error) {
        }
    }

    /**
     * Restore the remembered view and start recording changes.
     *
     * @returns {boolean} True once the map has been found and wired up.
     */
    function attach() {
        var map = (window.larentals || {}).map;
        if (!map || typeof map.setView !== "function") return false;
        if (restored) return true;
        restored = true;

        var saved = readSaved();
        if (saved) {
            var zoom = Math.min(Math.max(saved.zoom, map.getMinZoom()), map.getMaxZoom());
            map.setView([saved.lat, saved.lng], zoom, { animate: false });
        }

        map.on("moveend zoomend", function () {
            window.clearTimeout(saveTimer);
            saveTimer = window.setTimeout(function () { save(map); }, SAVE_DELAY_MS);
        });
        return true;
    }

    var poll = window.setInterval(function () {
        if (attach()) window.clearInterval(poll);
    }, 200);
    window.setTimeout(function () { window.clearInterval(poll); }, 30000);
})();
