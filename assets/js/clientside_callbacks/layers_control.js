/**
 * Enhance every Leaflet layers control with a click-driven disclosure and
 * publish the viewport event consumed by the responsive filter UI.
 *
 * Leaflet only omits its mouseenter/mouseleave handlers when the underlying
 * control is constructed with `collapsed: false`. The Python factory does
 * that, and this module then owns the visible collapsed/expanded state.
 */
(function () {
  const DESKTOP_BREAKPOINT = 1100;
  const VIEWPORT_EVENT_NAME = "viewportchange";
  const CONTROL_SELECTOR = ".leaflet-control-layers";
  const LIST_SELECTOR = ".leaflet-control-layers-list";
  const DISCOVERY_STORAGE_KEY = "wttl.layers-control-discovery.v1";
  const DISCOVERY_TIMEOUT_MS = 7000;

  let controlSequence = 0;

  /** @typedef {{width: number, isMobile: boolean}} ViewportDetail */
  /** @typedef {{focusButton?: boolean}} ExpansionOptions */
  /** @typedef {() => void} DismissHint */

  /**
   * Return the best available viewport width for responsive map controls.
   *
   * @returns {number} Viewport width in CSS pixels, or zero when unavailable.
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
   * Broadcast debounced viewport changes for Dash components that share the
   * layers-control breakpoint.
   *
   * @returns {void}
   */
  function setupViewportEvents() {
    /** @type {number | null} */
    let resizeTimer = null;
    /** @type {ViewportDetail | null} */
    let lastViewportState = null;

    /** @returns {void} */
    function dispatchViewportChange() {
      const width = getViewportWidth();
      /** @type {ViewportDetail} */
      const detail = { width, isMobile: width < DESKTOP_BREAKPOINT };

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

    /** @returns {void} */
    function scheduleViewportChange() {
      if (resizeTimer !== null) window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(dispatchViewportChange, 100);
    }

    window.addEventListener("resize", scheduleViewportChange, { passive: true });
    window.addEventListener("orientationchange", scheduleViewportChange, { passive: true });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", dispatchViewportChange, { once: true });
    } else {
      dispatchViewportChange();
    }

    window.addEventListener("load", dispatchViewportChange, { once: true });
  }

  /**
   * Determine whether this browser has already received the discovery hint.
   *
   * @returns {boolean} Whether the hint was recorded in local storage.
   */
  function discoveryHasBeenShown() {
    try {
      return window.localStorage.getItem(DISCOVERY_STORAGE_KEY) === "shown";
    } catch (_error) {
      return false;
    }
  }

  /**
   * Record that the discovery hint has been presented.
   *
   * Storage failures are intentionally ignored because the disclosure remains
   * fully usable without persistence.
   *
   * @returns {void}
   */
  function rememberDiscovery() {
    try {
      window.localStorage.setItem(DISCOVERY_STORAGE_KEY, "shown");
    } catch (_error) {
      // Storage can be unavailable in privacy modes; the control still works.
    }
  }

  /**
   * Add the one-time desktop discovery hint beside a disclosure button.
   *
   * The hint dismisses itself after an idle timeout, pauses while hovered or
   * focused, and can always be closed explicitly.
   *
   * @param {HTMLElement} control Enhanced Leaflet layers-control container.
   * @param {HTMLButtonElement} disclosureButton Button that opens the panel.
   * @returns {DismissHint} Idempotent callback that removes the hint.
   */
  function addDiscoveryHint(control, disclosureButton) {
    if (getViewportWidth() < DESKTOP_BREAKPOINT || discoveryHasBeenShown()) {
      return function noop() {};
    }

    rememberDiscovery();

    const hint = document.createElement("div");
    hint.className = "layers-control-discovery";
    hint.setAttribute("role", "note");
    hint.setAttribute("aria-label", "Map layers tip");

    const copy = document.createElement("span");
    copy.textContent = "More map layers available";

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "layers-control-discovery__close";
    closeButton.setAttribute("aria-label", "Dismiss map layers tip");
    closeButton.textContent = "\u00d7";

    hint.append(copy, closeButton);
    disclosureButton.insertAdjacentElement("afterend", hint);

    let dismissed = false;
    /** @type {number | null} */
    let timeoutId = null;

    /** @returns {void} */
    function dismissHint() {
      if (dismissed) return;
      dismissed = true;
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      hint.remove();
    }

    /** @returns {void} */
    function dismissWhenIdle() {
      if (hint.matches(":hover") || hint.contains(document.activeElement)) {
        timeoutId = window.setTimeout(dismissWhenIdle, 1000);
        return;
      }
      dismissHint();
    }

    closeButton.addEventListener("click", function onHintClose(event) {
      event.preventDefault();
      event.stopPropagation();
      dismissHint();
      disclosureButton.focus();
    });

    timeoutId = window.setTimeout(dismissWhenIdle, DISCOVERY_TIMEOUT_MS);
    return dismissHint;
  }

  /**
   * Enhance one Leaflet layers control with an accessible disclosure button.
   *
   * Enhancement is idempotent. The function synchronizes CSS, the panel's
   * `hidden` state, and `aria-expanded`; it also supports Escape and outside
   * pointer dismissal without closing while users operate layer inputs.
   *
   * @param {HTMLElement} control Leaflet layers-control container to enhance.
   * @returns {void}
   */
  function enhanceLayersControl(control) {
    if (control.dataset.layersDisclosure === "ready") return;

    /** @type {HTMLElement | null} */
    const list = control.querySelector(LIST_SELECTOR);
    if (!list) return;

    control.dataset.layersDisclosure = "ready";
    control.classList.add("layers-control-disclosure");
    control.removeAttribute("aria-haspopup");

    /** @type {HTMLElement | null} */
    const nativeToggle = control.querySelector(".leaflet-control-layers-toggle");
    if (nativeToggle) {
      nativeToggle.hidden = true;
      nativeToggle.setAttribute("aria-hidden", "true");
      nativeToggle.setAttribute("tabindex", "-1");
    }

    controlSequence += 1;
    if (!list.id) list.id = `map-layers-panel-${controlSequence}`;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "layers-control-disclosure__button";
    button.setAttribute("aria-controls", list.id);

    const label = document.createElement("span");
    label.textContent = "Layers";

    const chevron = document.createElement("span");
    chevron.className = "layers-control-disclosure__chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.textContent = "\u25be";

    button.append(label, chevron);
    control.insertBefore(button, list);

    let expanded = false;
    /** @type {DismissHint} */
    let dismissHint = function noop() {};

    /**
     * Synchronize the visual and accessible expanded state.
     *
     * @param {boolean} nextExpanded Whether the layer choices should be shown.
     * @param {ExpansionOptions=} options Optional focus-restoration behavior.
     * @returns {void}
     */
    function setExpanded(nextExpanded, options) {
      expanded = Boolean(nextExpanded);
      control.classList.toggle("leaflet-control-layers-expanded", expanded);
      control.classList.toggle("layers-control-disclosure--open", expanded);
      button.setAttribute("aria-expanded", String(expanded));
      button.setAttribute("aria-label", expanded ? "Collapse map layers" : "Show map layers");
      button.title = expanded ? "Collapse map layers" : "Show map layers";
      list.hidden = !expanded;

      if (expanded) dismissHint();
      if (options && options.focusButton) button.focus();
    }

    button.addEventListener("click", function toggleLayers(event) {
      event.preventDefault();
      event.stopPropagation();
      setExpanded(!expanded);
    });

    control.addEventListener("keydown", function closeLayersWithEscape(event) {
      if (event.key !== "Escape" || !expanded) return;
      event.preventDefault();
      event.stopPropagation();
      setExpanded(false, { focusButton: true });
    });

    document.addEventListener("pointerdown", function closeLayersFromOutside(event) {
      if (
        expanded &&
        event.target instanceof Node &&
        !control.contains(event.target)
      ) {
        setExpanded(false);
      }
    });

    setExpanded(false);
    dismissHint = addDiscoveryHint(control, button);
  }

  /**
   * Enhance all layers controls currently mounted in the document.
   *
   * @returns {void}
   */
  function enhanceAvailableControls() {
    document.querySelectorAll(CONTROL_SELECTOR).forEach((candidate) => {
      if (candidate instanceof HTMLElement) enhanceLayersControl(candidate);
    });
  }

  /**
   * Enhance existing controls and observe Dash/React mounts for new controls.
   *
   * @returns {void}
   */
  function setupLayersControls() {
    enhanceAvailableControls();

    const observer = new MutationObserver(enhanceAvailableControls);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  setupViewportEvents();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupLayersControls, { once: true });
  } else {
    setupLayersControls();
  }
})();
