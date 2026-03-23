const LAYERS_CONTROL_MOBILE_BREAKPOINT = 768;
const VIEWPORT_EVENT_NAME = "viewportchange";

/**
 * @typedef {{width: number, isMobile: boolean}} ViewportDetail
 */

/**
 * @typedef {Object} DashViewportEvent
 * @property {boolean=} detail.isMobile
 * @property {number=} detail.width
 */

/**
 * Return the current viewport width used by the layer-control breakpoint.
 *
 * @returns {number}
 */
function getViewportWidth() {
  return (
    window.innerWidth ||
    document.documentElement.clientWidth ||
    document.body.clientWidth ||
    0
  );
}

/**
 * Broadcast browser viewport changes through a document-level custom event.
 *
 * Dash listens for this event via `EventListener`, which lets us update
 * responsive component props without a server roundtrip.
 *
 * @returns {void}
 */
function setupViewportEvents() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  let resizeTimer = null;
  /** @type {ViewportDetail | null} */
  let lastViewportState = null;

  /**
   * Dispatch the current viewport details if they have changed.
   *
   * @returns {void}
   */
  function dispatchViewportChange() {
    const width = getViewportWidth();
    /** @type {ViewportDetail} */
    const detail = {
      width,
      isMobile: width < LAYERS_CONTROL_MOBILE_BREAKPOINT,
    };

    if (
      lastViewportState &&
      lastViewportState.width === detail.width &&
      lastViewportState.isMobile === detail.isMobile
    ) {
      return;
    }

    lastViewportState = detail;
    document.dispatchEvent(new CustomEvent(VIEWPORT_EVENT_NAME, { detail }));
  }

  /**
   * Debounce resize-driven updates so we do not flood Dash with events.
   *
   * @returns {void}
   */
  function scheduleViewportChange() {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(dispatchViewportChange, 100);
  }

  window.addEventListener("resize", scheduleViewportChange, { passive: true });
  window.addEventListener("orientationchange", scheduleViewportChange, { passive: true });

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      function onDomReady() {
        dispatchViewportChange();
        window.setTimeout(dispatchViewportChange, 150);
      },
      { once: true }
    );
  } else {
    dispatchViewportChange();
    window.setTimeout(dispatchViewportChange, 150);
  }

  window.addEventListener(
    "load",
    function onWindowLoad() {
      dispatchViewportChange();
      window.setTimeout(dispatchViewportChange, 250);
    },
    { once: true }
  );
}

setupViewportEvents();

window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
    /**
     * Keep `LayersControl.collapsed` in sync with the current viewport.
     *
     * @param {number} _nIntervals
     * @param {DashViewportEvent | null | undefined} viewportEvent
     * @param {boolean | undefined} currentCollapsed
     * @returns {boolean}
     */
    layersControlCollapsed: function(_nIntervals, viewportEvent, currentCollapsed) {
      if (
        viewportEvent &&
        typeof viewportEvent["detail.isMobile"] === "boolean"
      ) {
        return viewportEvent["detail.isMobile"];
      }

      if (typeof window !== "undefined") {
        return getViewportWidth() < LAYERS_CONTROL_MOBILE_BREAKPOINT;
      }

      if (typeof currentCollapsed === "boolean") {
        return currentCollapsed;
      }

      return true;
    }
  })
});
