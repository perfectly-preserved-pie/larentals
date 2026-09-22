// Remember each listing page's map center and zoom in this browser.
(function () {
    "use strict";

    var SAVE_DELAY_MS = 400;
    var attachedMap = null;
    var pollTimer = null;

    function storageKey() {
        var path = String(window.location.pathname || "").toLowerCase();
        var page = path.indexOf("/buy") === 0 ? "buy" : "lease";
        return "larentals:map-view:" + page;
    }

    function readSaved(key) {
        try {
            var raw = window.localStorage.getItem(key);
            if (!raw) return null;
            var saved = JSON.parse(raw);
            if (!saved || typeof saved !== "object") return null;
            var lat = Number(saved.lat);
            var lng = Number(saved.lng);
            var zoom = Number(saved.zoom);
            if (!isFinite(lat) || !isFinite(lng) || !isFinite(zoom)) return null;
            if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
            return { lat: lat, lng: lng, zoom: zoom };
        } catch (error) {
            return null;
        }
    }

    function attach() {
        var map = (window.larentals || {}).map;
        if (!map || typeof map.setView !== "function") return false;
        if (map === attachedMap) return true;

        attachedMap = map;
        var key = storageKey();
        var saved = readSaved(key);
        if (saved) {
            var minZoom = typeof map.getMinZoom === "function" ? map.getMinZoom() : 0;
            var maxZoom = typeof map.getMaxZoom === "function" ? map.getMaxZoom() : 22;
            var zoom = Math.min(Math.max(saved.zoom, minZoom), maxZoom);
            map.setView([saved.lat, saved.lng], zoom, { animate: false });
        }

        var saveTimer = null;
        function saveView() {
            window.clearTimeout(saveTimer);
            saveTimer = window.setTimeout(function () {
                try {
                    var center = map.getCenter();
                    window.localStorage.setItem(key, JSON.stringify({
                        lat: center.lat,
                        lng: center.lng,
                        zoom: map.getZoom(),
                    }));
                } catch (error) {
                    // Storage may be disabled; map interaction should still work.
                }
            }, SAVE_DELAY_MS);
        }
        map.on("moveend zoomend", saveView);
        map.on("unload", function () {
            window.clearTimeout(saveTimer);
            saveView();
        });
        return true;
    }

    pollTimer = window.setInterval(function () {
        // Dash can replace the Leaflet map when the page layout is rebuilt.
        // Keep checking so the current map always gets persistence handlers.
        attach();
    }, 500);
    attach();
})();
