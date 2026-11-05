(function () {
  "use strict";

  const root = window.larentals = window.larentals || {};
  const states = {};
  const bindings = {};
  const DESKTOP_BREAKPOINT = 1100;

  /**
   * Keep Leaflet's viewport and the column buttons aligned with actual pane widths.
   * ResizeObserver runs during dragging, while Dash's sizes prop commits on release.
   * @param {HTMLElement} layout Mounted listing shell whose panes changed size.
   * @returns {void}
   */
  function updateGeometry(layout) {
    if (!layout.isConnected) return;
    const filter = layout.querySelector(".listing-filter-pane");
    const results = layout.querySelector(".listing-results-pane");
    if (window.innerWidth >= DESKTOP_BREAKPOINT) {
      layout.style.setProperty("--filter-panel-width", `${filter.getBoundingClientRect().width}px`);
      layout.style.setProperty("--results-panel-width", `${results.getBoundingClientRect().width}px`);
    }
    const map = root.mapGestureControls?.getMap?.();
    if (map && layout.contains(map.getContainer())) {
      map.invalidateSize({ animate: false, debounceMoveend: true });
    }
  }

  /**
   * Bind the current page's panes without retaining observers on replaced layouts.
   * Buy/rent navigation replaces the shell, so an old observer must be disconnected.
   * @param {string} page Listing mode used to scope observers.
   * @param {HTMLElement} layout Current listing shell.
   * @returns {void}
   */
  function observeLayout(page, layout) {
    if (bindings[page]?.layout === layout) return;
    bindings[page]?.observer.disconnect();
    let frame = null;
    const observer = new ResizeObserver(() => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = null;
        updateGeometry(layout);
      });
    });
    layout.querySelectorAll(".listing-splitter-pane, .listing-map-col").forEach(node => observer.observe(node));
    bindings[page] = { layout, observer };
    const handles = layout.querySelectorAll('.listing-splitter > [role="separator"]');
    ["Resize filters and map", "Resize map and listings"].forEach((label, index) => {
      handles[index]?.setAttribute("aria-label", label);
    });
    updateGeometry(layout);
  }

  /**
   * Mirror native pane collapse into the shell's accessibility and detail placement.
   * Mobile uses the same filter tree as a sheet, regardless of desktop collapse state.
   * @param {HTMLElement} layout Listing shell containing both sidebars.
   * @param {number[]} collapsed Native Splitter indices, where 0 and 2 are sidebars.
   * @returns {void}
   */
  function reflectCollapsed(layout, collapsed) {
    const desktop = window.innerWidth >= DESKTOP_BREAKPOINT;
    for (const [column, index] of [["filters", 0], ["results", 2]]) {
      const hidden = desktop && collapsed.includes(index);
      layout.classList.toggle(`is-${column}-hidden`, hidden);
      const button = layout.querySelector(`[data-column-toggle="${column}"]`);
      if (button) {
        button.setAttribute("aria-expanded", String(!hidden));
        const label = button.getAttribute(hidden ? "data-tooltip-show" : "data-tooltip-hide");
        button.setAttribute("aria-label", label);
        button.setAttribute("data-tooltip", label);
      }
      const panel = layout.querySelector(column === "filters" ? ".responsive-filter-panel" : ".results-panel");
      if (panel) panel.inert = hidden;
    }
    root.listingDetail?.rehome?.();
  }

  /**
   * Send an existing column button's desired visibility to the native Splitter.
   * The explicit hidden state avoids toggling twice when its prop update returns.
   * @param {string} page Listing mode owning the clicked button.
   * @param {string} column Filters or results sidebar.
   * @param {boolean} hidden Whether that sidebar should be collapsed.
   * @returns {void}
   */
  function setPanelHidden(page, column, hidden) {
    const index = column === "filters" ? 0 : 2;
    const collapsed = new Set(states[page]?.collapsed || []);
    if (hidden) collapsed.add(index);
    else collapsed.delete(index);
    window.dash_clientside.set_props(`${page}-listing-splitter`, { collapsed: [...collapsed].sort() });
  }

  /**
   * Bridge persisted pane props to native buttons and map-size observation.
   * This stays clientside so dragging never starts a Python callback or recreates filters.
   * @param {Array<number|string>} sizes Native pane sizes, including their original units.
   * @param {number[]} collapsed Indices of currently collapsed panes.
   * @param {string} identifier Page-scoped Splitter identifier.
   * @returns {object} Current pane state retained in the page's memory store.
   */
  function syncListingSplitter(sizes, collapsed, identifier) {
    const page = identifier.replace("-listing-splitter", "");
    const state = { sizes: sizes || [], collapsed: (collapsed || []).filter(index => index === 0 || index === 2) };
    states[page] = state;
    const layout = document.querySelector(`[data-listing-page="${page}"]`);
    if (layout) {
      observeLayout(page, layout);
      reflectCollapsed(layout, state.collapsed);
    }
    return state;
  }

  window.addEventListener("resize", () => {
    for (const [page, state] of Object.entries(states)) {
      const layout = document.querySelector(`[data-listing-page="${page}"]`);
      if (layout) reflectCollapsed(layout, state.collapsed);
    }
  }, { passive: true });

  root.listingSplitter = { setPanelHidden, states };
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: Object.assign({}, window.dash_clientside?.clientside, { syncListingSplitter }),
  });
})();
