(function () {
    "use strict";

    const LAHD_RECORD_EVENT_NAME = "lahdrecordrequest";
    const TRIGGER_SELECTOR = "[data-lahd-records-trigger='true']";

    /**
     * Normalize a nullable DOM attribute value.
     *
     * @param {unknown} value Raw attribute value.
     * @returns {string|null} Trimmed string or null.
     */
    function normalizeAttribute(value) {
        if (value === null || value === undefined) return null;
        const normalized = String(value).trim();
        return normalized ? normalized : null;
    }

    /**
     * Dispatch a Dash-visible LAHD record request event.
     *
     * @param {Record<string, unknown>} detail Request detail.
     * @returns {void}
     */
    function dispatchLahdRecordRequest(detail) {
        const apn = normalizeAttribute(detail.apn);
        if (!apn || typeof document === "undefined") return;

        document.dispatchEvent(
            new CustomEvent(LAHD_RECORD_EVENT_NAME, {
                detail: {
                    apn,
                    address: normalizeAttribute(detail.address),
                    source: normalizeAttribute(detail.source),
                    requestedAt: Date.now(),
                },
            }),
        );
    }

    /**
     * Handle clicks from Leaflet popup record buttons.
     *
     * @param {MouseEvent} event Browser click event.
     * @returns {void}
     */
    function handleRecordsTriggerClick(event) {
        const rawTarget = event.target;
        const target = rawTarget && rawTarget.closest
            ? rawTarget.closest(TRIGGER_SELECTOR)
            : null;

        if (!target) return;

        event.preventDefault();
        event.stopPropagation();

        dispatchLahdRecordRequest({
            apn: target.getAttribute("data-lahd-apn"),
            address: target.getAttribute("data-lahd-address"),
            source: target.getAttribute("data-lahd-source"),
        });
    }

    if (typeof document !== "undefined") {
        document.addEventListener("click", handleRecordsTriggerClick, true);
    }

    window.larentals = Object.assign({}, window.larentals, {
        lahd: Object.assign({}, window.larentals && window.larentals.lahd, {
            dispatchRecordRequest: dispatchLahdRecordRequest,
            recordRequestEventName: LAHD_RECORD_EVENT_NAME,
        }),
    });
})();
