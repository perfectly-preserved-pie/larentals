(function () {
  "use strict";

  /** @typedef {"lease" | "buy"} ListingPage */
  /** @typedef {Object<string, *>} FilterState */
  /** @typedef {{type: string, features: Array<Object>}} FeatureCollection */

  const DESKTOP_BREAKPOINT = 1100;
  const root = window.larentals = window.larentals || {};
  const filtersApi = root.filters = root.filters || {};
  const ui = root.responsiveFilters = root.responsiveFilters || {};

  ui.defaults = ui.defaults || {};
  ui.drafts = ui.drafts || {};
  ui.applied = ui.applied || {};
  ui.previewCounts = ui.previewCounts || {};
  ui.appliedCounts = ui.appliedCounts || {};
  ui.forceApplyUntil = ui.forceApplyUntil || {};
  ui.pendingApplyAnalytics = ui.pendingApplyAnalytics || {};
  ui.pendingLocationApply = ui.pendingLocationApply || {};
  ui.restoring = ui.restoring || {};
  ui.openedAt = ui.openedAt || {};
  ui.pageStartedAt = ui.pageStartedAt || {};

  const CONTROL_MAP = Object.freeze({
    lease: Object.freeze({
      priceRange: ["rental_price_slider", "value"],
      bedroomsRange: ["bedrooms_slider", "value"],
      bathroomsRange: ["bathrooms_slider", "value"],
      pets: ["pets_radio", "value"],
      sqftRange: ["sqft_slider", "value"],
      sqftMissing: ["sqft_missing_switch", "checked"],
      ppsqftRange: ["ppsqft_slider", "value"],
      ppsqftMissing: ["ppsqft_missing_switch", "checked"],
      parkingRange: ["garage_spaces_slider", "value"],
      parkingMissing: ["garage_missing_switch", "checked"],
      yearRange: ["yrbuilt_slider", "value"],
      yearMissing: ["yrbuilt_missing_switch", "checked"],
      terms: ["terms_checklist", "value"],
      termsMissing: ["terms_missing_switch", "checked"],
      furnished: ["furnished_checklist", "value"],
      furnishedMissing: ["furnished_missing_switch", "checked"],
      securityRange: ["security_deposit_slider", "value"],
      securityMissing: ["security_deposit_missing_switch", "checked"],
      petDepositRange: ["pet_deposit_slider", "value"],
      petDepositMissing: ["pet_deposit_missing_switch", "checked"],
      keyDepositRange: ["key_deposit_slider", "value"],
      keyDepositMissing: ["key_deposit_missing_switch", "checked"],
      otherDepositRange: ["other_deposit_slider", "value"],
      otherDepositMissing: ["other_deposit_missing_switch", "checked"],
      laundry: ["laundry_checklist", "value"],
      laundryMissing: ["laundry_missing_switch", "checked"],
      subtypes: ["subtype_checklist", "value"],
      listedRange: ["listed_time_range_radio", "value"],
      dateStart: ["listed_date_datepicker_lease", "start_date"],
      dateEnd: ["listed_date_datepicker_lease", "end_date"],
      dateMissing: ["listed_date_missing_switch", "checked"],
      downloadRange: ["isp_download_speed_slider", "value"],
      uploadRange: ["isp_upload_speed_slider", "value"],
      ispMissing: ["isp_speed_missing_switch", "checked"],
      rentControl: ["rent_control_status", "value"],
      locationText: ["lease-location-input", "value"],
      nearbyZip: ["lease-nearby-zip-switch", "checked"],
      zipBoundary: ["lease-zip-boundary-store", "data"],
    }),
    buy: Object.freeze({
      priceRange: ["list_price_slider", "value"],
      bedroomsRange: ["bedrooms_slider", "value"],
      bathroomsRange: ["bathrooms_slider", "value"],
      sqftRange: ["sqft_slider", "value"],
      sqftMissing: ["sqft_missing_switch", "checked"],
      ppsqftRange: ["ppsqft_slider", "value"],
      ppsqftMissing: ["ppsqft_missing_switch", "checked"],
      lotSizeRange: ["lot_size_slider", "value"],
      lotSizeMissing: ["lot_size_missing_switch", "checked"],
      yearRange: ["yrbuilt_slider", "value"],
      yearMissing: ["yrbuilt_missing_switch", "checked"],
      subtypes: ["subtype_checklist", "value"],
      listedRange: ["listed_time_range_radio", "value"],
      dateStart: ["listed_date_datepicker_buy", "start_date"],
      dateEnd: ["listed_date_datepicker_buy", "end_date"],
      dateMissing: ["listed_date_missing_switch", "checked"],
      hoaRange: ["hoa_fee_slider", "value"],
      hoaMissing: ["hoa_fee_missing_switch", "checked"],
      hoaFrequency: ["hoa_fee_frequency_checklist", "value"],
      downloadRange: ["isp_download_speed_slider", "value"],
      uploadRange: ["isp_upload_speed_slider", "value"],
      ispMissing: ["isp_speed_missing_switch", "checked"],
      locationText: ["buy-location-input", "value"],
      nearbyZip: ["buy-nearby-zip-switch", "checked"],
      zipBoundary: ["buy-zip-boundary-store", "data"],
    }),
  });

  const GROUPS = Object.freeze({
    lease: Object.freeze({
      location: ["locationText", "nearbyZip"],
      price: ["priceRange"],
      bedrooms: ["bedroomsRange"],
      bathrooms: ["bathroomsRange"],
      pets: ["pets"],
      sqft: ["sqftRange", "sqftMissing"],
      ppsqft: ["ppsqftRange", "ppsqftMissing"],
      parking: ["parkingRange", "parkingMissing"],
      year: ["yearRange", "yearMissing"],
      terms: ["terms", "termsMissing"],
      furnished: ["furnished", "furnishedMissing"],
      deposits: [
        "securityRange", "securityMissing", "petDepositRange",
        "petDepositMissing", "keyDepositRange", "keyDepositMissing",
        "otherDepositRange", "otherDepositMissing",
      ],
      laundry: ["laundry", "laundryMissing"],
      subtypes: ["subtypes"],
      listedDate: ["listedRange", "dateStart", "dateEnd", "dateMissing"],
      isp: ["downloadRange", "uploadRange", "ispMissing"],
      rentControl: ["rentControl"],
    }),
    buy: Object.freeze({
      location: ["locationText", "nearbyZip"],
      price: ["priceRange"],
      bedrooms: ["bedroomsRange"],
      bathrooms: ["bathroomsRange"],
      sqft: ["sqftRange", "sqftMissing"],
      ppsqft: ["ppsqftRange", "ppsqftMissing"],
      lotSize: ["lotSizeRange", "lotSizeMissing"],
      year: ["yearRange", "yearMissing"],
      subtypes: ["subtypes"],
      listedDate: ["listedRange", "dateStart", "dateEnd", "dateMissing"],
      hoa: ["hoaRange", "hoaMissing"],
      hoaFrequency: ["hoaFrequency"],
      isp: ["downloadRange", "uploadRange", "ispMissing"],
    }),
  });

  /**
   * Copy a JSON-compatible value without retaining mutable references.
   * @template T
   * @param {T} value Value to copy.
   * @returns {T} Independent copy of the value.
   */
  function clone(value) {
    if (value === undefined) return undefined;
    return JSON.parse(JSON.stringify(value));
  }

  /**
   * Compare two JSON-compatible values by content.
   * @param {*} left First value.
   * @param {*} right Second value.
   * @returns {boolean} Whether both values serialize identically.
   */
  function equal(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
  }

  /**
   * Format the location control's string or tag-array value consistently.
   * @param {*} value Current location control value.
   * @returns {string} Human-readable location list.
   */
  function locationText(value) {
    if (Array.isArray(value)) {
      return value.map(function (item) { return String(item || "").trim(); })
        .filter(Boolean)
        .join(", ");
    }
    return String(value || "").trim();
  }

  /**
   * Serialize a location value without collapsing tag boundaries.
   * @param {*} value Current location control value.
   * @returns {string} Stable comparison key for pending location updates.
   */
  function locationValueKey(value) {
    return JSON.stringify(Array.isArray(value) ? value : String(value || ""));
  }

  /**
   * Identify the listing mode represented by the current URL.
   * @returns {ListingPage} Current Rent or Buy page key.
   */
  function currentPage() {
    const path = String(window.location && window.location.pathname || "").toLowerCase();
    return path === "/buy" || path.startsWith("/buy/") ? "buy" : "lease";
  }

  /**
   * Read the component IDs that triggered the active Dash callback.
   * @returns {string[]} Triggering component IDs without property suffixes.
   */
  function triggeredIds() {
    const context = window.dash_clientside && window.dash_clientside.callback_context;
    if (!context || !Array.isArray(context.triggered)) return [];
    return context.triggered.map(function (item) {
      return String(item && item.prop_id || "").split(".")[0];
    }).filter(Boolean);
  }

  /**
   * Find filter groups whose values differ from the page defaults.
   * @param {ListingPage} page Listing mode to inspect.
   * @param {FilterState} state Filter values to compare.
   * @returns {string[]} Names of active filter groups.
   */
  function activeGroups(page, state) {
    const defaults = ui.defaults[page];
    if (!state || !defaults) return [];
    return Object.keys(GROUPS[page]).filter(function (groupName) {
      return GROUPS[page][groupName].some(function (key) {
        return !equal(state[key], defaults[key]);
      });
    });
  }

  /**
   * Decide whether captured controls remain a draft or update the map.
   * @param {ListingPage} page Listing mode being updated.
   * @param {FilterState} state Newly captured control values.
   * @param {FilterState | null} currentApplied Last committed filter values.
   * @returns {Array<*>} Draft and applied values expected by Dash outputs.
   */
  function finalizeCapture(page, state, currentApplied) {
    const ids = triggeredIds();
    const applyId = `${page}-filter-apply-button`;
    const zipStoreId = `${page}-zip-boundary-store`;
    const viewportOnly = ids.length === 1 && ids[0] === "viewport-listener";
    const isInitial = !currentApplied;
    const forced = Number(ui.forceApplyUntil[page] || 0) >= Date.now();
    const pendingLocation = ui.pendingLocationApply[page];
    const restoring = ui.restoring[page];
    if (restoring && restoring.expires >= Date.now()) {
      ui.drafts[page] = clone(restoring.state);
      scheduleRender(page);
      return [restoring.state, window.dash_clientside.no_update];
    }
    if (restoring) delete ui.restoring[page];

    const completesPendingLocation = Boolean(
      ids.includes(zipStoreId) &&
      pendingLocation &&
      pendingLocation.expires >= Date.now() &&
      pendingLocation.valueKey === locationValueKey(state.locationText)
    );
    const shouldApply = isInitial || window.innerWidth >= DESKTOP_BREAKPOINT ||
      ids.includes(applyId) || forced || completesPendingLocation;

    if (!ui.defaults[page] || isInitial) {
      ui.defaults[page] = clone(state);
    }
    ui.drafts[page] = clone(state);

    if (currentApplied && !ui.applied[page]) {
      ui.applied[page] = clone(currentApplied);
    }

    if (!viewportOnly && page === "lease") {
      root.analytics?.trackLeaseFilterChanges?.();
    } else if (!viewportOnly && page === "buy") {
      root.analytics?.trackBuyFilterChanges?.();
    }

    if (shouldApply) {
      ui.applied[page] = clone(state);
      if (ids.includes(applyId)) {
        ui.pendingApplyAnalytics[page] = true;
        const pendingLocationText = locationText(state.locationText);
        if (pendingLocationText) {
          ui.pendingLocationApply[page] = {
            valueKey: locationValueKey(state.locationText),
            expires: Date.now() + 15_000,
          };
        } else {
          delete ui.pendingLocationApply[page];
        }
      }
      if (completesPendingLocation) {
        delete ui.pendingLocationApply[page];
      }
      scheduleRender(page);
      return [state, state];
    }

    scheduleRender(page);
    return [state, window.dash_clientside.no_update];
  }

  /**
   * Run the page-specific filter engine against the source listings.
   * @param {ListingPage} page Listing mode being filtered.
   * @param {FilterState} state Filter values to apply.
   * @param {FeatureCollection} fullGeojson Unfiltered listing features.
   * @returns {FeatureCollection | null} Filtered features when inputs are ready.
   */
  function filterState(page, state, fullGeojson) {
    if (!state || !fullGeojson || !Array.isArray(fullGeojson.features)) {
      return null;
    }
    if (page === "lease" && typeof filtersApi.filterLeaseState === "function") {
      return filtersApi.filterLeaseState(state, fullGeojson);
    }
    if (page === "buy" && typeof filtersApi.filterBuyState === "function") {
      return filtersApi.filterBuyState(state, fullGeojson);
    }
    return null;
  }

  /**
   * Calculate and store the result count for uncommitted filter values.
   * @param {ListingPage} page Listing mode being previewed.
   * @param {FilterState} state Draft filter values.
   * @param {FeatureCollection} fullGeojson Unfiltered listing features.
   * @returns {{count: number | null, updatedAt?: number}} Preview metadata.
   */
  function preview(page, state, fullGeojson) {
    const result = filterState(page, state, fullGeojson);
    if (!result) return { count: null };
    const count = result.features.length;
    ui.previewCounts[page] = count;
    scheduleRender(page);
    return { count, updatedAt: Date.now() };
  }

  /**
   * Apply committed filter values and update result-count analytics.
   * @param {ListingPage} page Listing mode being filtered.
   * @param {FilterState} state Committed filter values.
   * @param {FeatureCollection} fullGeojson Unfiltered listing features.
   * @returns {FeatureCollection | *} Filtered features or Dash's no-update value.
   */
  function apply(page, state, fullGeojson) {
    const result = filterState(page, state, fullGeojson);
    if (!result) return window.dash_clientside.no_update;

    const count = result.features.length;
    ui.applied[page] = clone(state);
    ui.appliedCounts[page] = count;

    if (ui.pendingApplyAnalytics[page]) {
      ui.pendingApplyAnalytics[page] = false;
      root.analytics?.trackEvent?.("Filters Applied", {
        page,
        ui: "adaptive-sheet-v1",
        active_filters: activeGroups(page, state).length,
        results: resultBucket(count),
      });
    }

    scheduleRender(page);
    return result;
  }

  /**
   * Reduce an exact result count to a low-cardinality analytics label.
   * @param {number} count Number of matching listings.
   * @returns {string} Analytics bucket for the count.
   */
  function resultBucket(count) {
    if (count === 0) return "0";
    if (count < 10) return "1-9";
    if (count < 50) return "10-49";
    if (count < 200) return "50-199";
    return "200+";
  }

  /**
   * Format a numeric value for compact interface copy.
   * @param {*} value Value that can be converted to a number.
   * @returns {string} Locale-formatted number.
   */
  function formatNumber(value) {
    return new Intl.NumberFormat("en-US").format(Number(value || 0));
  }

  /**
   * Format a price using compact US-dollar notation when appropriate.
   * @param {*} value Value that can be converted to a number.
   * @returns {string} Human-readable dollar amount.
   */
  function compactCurrency(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "$0";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      notation: Math.abs(amount) >= 1000 ? "compact" : "standard",
      maximumFractionDigits: 1,
    }).format(amount);
  }

  /**
   * Describe an active numeric range in a quick-filter chip.
   * @param {string} label Short filter name.
   * @param {number[]} value Current lower and upper bounds.
   * @param {number[]} defaults Default lower and upper bounds.
   * @param {boolean} currency Whether bounds represent currency.
   * @returns {string} Concise range label.
   */
  function rangeLabel(label, value, defaults, currency) {
    if (!Array.isArray(value) || !Array.isArray(defaults)) return label;
    const formatter = currency ? compactCurrency : function (number) { return String(number); };
    if (equal(value, defaults)) return label;
    if (value[0] === defaults[0]) return `${label} ≤ ${formatter(value[1])} ×`;
    if (value[1] === defaults[1]) return `${label} ≥ ${formatter(value[0])} ×`;
    return `${label} ${formatter(value[0])}–${formatter(value[1])} ×`;
  }

  /**
   * Update one quick-filter chip to reflect its applied value.
   * @param {ListingPage} page Listing mode being rendered.
   * @param {string} group Filter group represented by the chip.
   * @param {FilterState} state Applied filter values.
   * @param {FilterState} defaults Default filter values.
   * @returns {void}
   */
  function renderChip(page, group, state, defaults) {
    const button = document.getElementById(`${page}-quick-${group}`);
    if (!button) return;

    const active = activeGroups(page, state).includes(group);
    let text = button.dataset.defaultLabel || button.textContent || group;
    if (!button.dataset.defaultLabel) button.dataset.defaultLabel = text;

    if (active) {
      if (group === "location") {
        const location = locationText(state.locationText) || "Selected area";
        text = `${location.length > 22 ? `${location.slice(0, 21)}…` : location} ×`;
      } else if (group === "price") {
        text = rangeLabel(page === "lease" ? "Rent" : "Price", state.priceRange, defaults.priceRange, true);
      } else if (group === "bedrooms") {
        text = rangeLabel("Beds", state.bedroomsRange, defaults.bedroomsRange, false);
      } else if (group === "bathrooms") {
        text = rangeLabel("Baths", state.bathroomsRange, defaults.bathroomsRange, false);
      } else if (group === "pets") {
        text = `${state.pets === true ? "Pets allowed" : "No pets"} ×`;
      }
    }

    button.textContent = text;
    button.classList.toggle("map-filter-chip--active", active);
    button.setAttribute(
      "aria-label",
      active ? `Remove ${button.dataset.defaultLabel} filter` : `Open ${button.dataset.defaultLabel} filters`
    );
  }

  /**
   * Keep location-entry instructions aligned with the device and tag state.
   * @param {ListingPage} page Listing mode to update.
   * @returns {void}
   */
  function setLocationInputCues(page) {
    const input = document.getElementById(`${page}-location-input`);
    if (input instanceof HTMLInputElement) {
      input.setAttribute("enterkeyhint", "next");
      const value = ui.drafts[page] && ui.drafts[page].locationText;
      const hasLocation = Array.isArray(value)
        ? value.some(function (item) { return String(item || "").trim(); })
        : Boolean(String(value || "").trim());
      const action = window.matchMedia("(pointer: coarse)").matches
        ? "tap Next"
        : "press Enter";
      input.setAttribute(
        "placeholder",
        `Type ${hasLocation ? "another" : "a"} location, then ${action}`
      );
    }
  }

  /**
   * Synchronize toolbar labels, counts, and chips with filter state.
   * @param {ListingPage} page Listing mode to render.
   * @returns {void}
   */
  function render(page) {
    setLocationInputCues(page);

    const appliedState = ui.applied[page];
    const defaults = ui.defaults[page];
    if (!appliedState || !defaults) return;

    const active = activeGroups(page, appliedState);
    ["location", "price", "bedrooms", "bathrooms"].forEach(function (group) {
      renderChip(page, group, appliedState, defaults);
    });
    if (page === "lease") renderChip(page, "pets", appliedState, defaults);

    const more = document.getElementById(`${page}-quick-more`);
    const visibleGroups = page === "lease"
      ? new Set(["location", "price", "bedrooms", "bathrooms", "pets"])
      : new Set(["location", "price", "bedrooms", "bathrooms"]);
    const advancedCount = active.filter(function (name) { return !visibleGroups.has(name); }).length;
    if (more) {
      more.textContent = advancedCount ? `More · ${advancedCount}` : "More";
      more.classList.toggle("map-filter-chip--active", advancedCount > 0);
      more.setAttribute("aria-label", advancedCount ? `Open filters; ${advancedCount} more active` : "Open more filters");
    }

    const badge = document.getElementById(`${page}-filter-count-badge`);
    if (badge) {
      badge.textContent = String(active.length);
      badge.hidden = active.length === 0;
    }

    const noun = page === "lease" ? "rentals" : "homes";
    const appliedCount = ui.appliedCounts[page];
    const previewCount = ui.previewCounts[page];
    const mapCount = document.getElementById(`${page}-map-result-count`);
    if (mapCount && Number.isFinite(appliedCount)) {
      mapCount.textContent = `${formatNumber(appliedCount)} ${noun}`;
    }

    const panelCount = document.getElementById(`${page}-filter-panel-count`);
    if (panelCount && Number.isFinite(previewCount)) {
      panelCount.textContent = `${formatNumber(previewCount)} matching ${noun}`;
    }

    const applyButton = document.getElementById(`${page}-filter-apply-button`);
    if (applyButton && Number.isFinite(previewCount)) {
      applyButton.textContent = `Show ${formatNumber(previewCount)} ${noun}`;
      applyButton.setAttribute("aria-label", `Apply filters and show ${formatNumber(previewCount)} matching ${noun}`);
    }
  }

  /**
   * Schedule a toolbar refresh on the browser's next paint.
   * @param {ListingPage} page Listing mode to render.
   * @returns {void}
   */
  function scheduleRender(page) {
    window.requestAnimationFrame(function () { render(page); });
  }

  /**
   * Write selected filter-state fields back to their Dash controls.
   * @param {ListingPage} page Listing mode whose controls should change.
   * @param {FilterState} state Values to restore.
   * @param {string[]} [keys] State fields to write; defaults to every field.
   * @returns {void}
   */
  function setStateProps(page, state, keys) {
    if (!state || !window.dash_clientside || typeof window.dash_clientside.set_props !== "function") {
      return;
    }
    const mapping = CONTROL_MAP[page];
    (keys || Object.keys(mapping)).forEach(function (key) {
      const target = mapping[key];
      if (!target || !(key in state)) return;
      const props = {};
      props[target[1]] = clone(state[key]);
      window.dash_clientside.set_props(target[0], props);
    });
  }

  /**
   * Reset one active filter group and immediately update the map.
   * @param {ListingPage} page Listing mode being changed.
   * @param {string} group Filter group to reset.
   * @returns {void}
   */
  function removeGroup(page, group) {
    const defaults = ui.defaults[page];
    const keys = GROUPS[page] && GROUPS[page][group];
    if (!defaults || !keys) return;
    delete ui.restoring[page];
    ui.forceApplyUntil[page] = Date.now() + 750;
    setStateProps(page, defaults, keys.concat(group === "location" ? ["zipBoundary"] : []));
    root.analytics?.trackEvent?.("Applied Filter Removed", { page, filter: group, ui: "adaptive-sheet-v1" });
  }

  /**
   * Restore every changed filter control to its page default.
   * @param {ListingPage} page Listing mode being cleared.
   * @returns {void}
   */
  function clearFilters(page) {
    const defaults = ui.defaults[page];
    if (!defaults) return;
    delete ui.restoring[page];
    const current = ui.drafts[page] || ui.applied[page] || {};
    const changedKeys = Object.keys(CONTROL_MAP[page]).filter(function (key) {
      return !equal(current[key], defaults[key]);
    });
    setStateProps(page, defaults, changedKeys);
    root.analytics?.trackEvent?.("Filters Cleared", { page, ui: "adaptive-sheet-v1" });
  }

  /**
   * Find the responsive filter panel for a listing page.
   * @param {ListingPage} page Listing mode to locate.
   * @returns {HTMLElement | null} Matching panel, when mounted.
   */
  function panelFor(page) {
    return document.querySelector(`[data-filter-panel='${page}']`);
  }

  /**
   * Find every control that can open a page's filter panel.
   * @param {ListingPage} page Listing mode to locate.
   * @returns {NodeListOf<HTMLElement>} Matching toolbar and prompt controls.
   */
  function toolbarTriggers(page) {
    return document.querySelectorAll(`[data-filter-open='${page}']`);
  }

  /**
   * Open the responsive panel and optionally focus a filter section.
   * @param {ListingPage} page Listing mode to open.
   * @param {HTMLElement | null} trigger Control that requested the panel.
   * @param {string} [section] Accordion section to reveal.
   * @returns {void}
   */
  function openPanel(page, trigger, section) {
    if (window.innerWidth >= DESKTOP_BREAKPOINT) {
      focusSection(page, section);
      return;
    }
    const panel = panelFor(page);
    const backdrop = document.getElementById(`${page}-filter-backdrop`);
    const main = document.getElementById(`${page}-map-main`);
    if (!panel || !backdrop) return;

    ui.lastTrigger = trigger || document.activeElement;
    ui.openedAt[page] = Date.now();
    panel.classList.add("is-open");
    backdrop.classList.add("is-open");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    document.body.classList.add("filter-panel-open");
    if (main) main.inert = true;
    toolbarTriggers(page).forEach(function (item) { item.setAttribute("aria-expanded", "true"); });

    const title = document.getElementById(`${page}-filter-panel-title`);
    window.setTimeout(function () {
      (title || panel).focus({ preventScroll: true });
      focusSection(page, section);
    }, 180);

    root.analytics?.trackEvent?.("Filter Drawer Opened", {
      page,
      source: trigger && trigger.dataset.filterSource || "unknown",
      presentation: window.innerWidth < 768 ? "bottom-sheet" : "side-drawer",
      ui: "adaptive-sheet-v1",
    });
  }

  /**
   * Close the responsive panel and optionally discard draft edits.
   * @param {ListingPage} page Listing mode to close.
   * @param {string} source Interaction used to close the panel.
   * @param {boolean} restore Whether applied values should replace the draft.
   * @returns {void}
   */
  function closePanel(page, source, restore) {
    const panel = panelFor(page);
    const backdrop = document.getElementById(`${page}-filter-backdrop`);
    const main = document.getElementById(`${page}-map-main`);
    if (!panel || !panel.classList.contains("is-open")) return;

    if (restore) {
      const applied = ui.applied[page] || {};
      const draft = ui.drafts[page] || {};
      const locationKeys = new Set(["locationText", "nearbyZip", "zipBoundary"]);
      const changedKeys = Object.keys(CONTROL_MAP[page]).filter(function (key) {
        // Local controls are cheap to restore and this closes the rapid-dismiss race.
        if (!locationKeys.has(key)) return true;
        // Location changes invoke geocoding callbacks, so only restore them when needed.
        return !equal(draft[key], applied[key]);
      });
      ui.restoring[page] = {
        state: clone(applied),
        expires: Date.now() + 350,
      };
      ui.drafts[page] = clone(applied);
      setStateProps(page, applied, changedKeys);
    }
    panel.classList.remove("is-open");
    backdrop?.classList.remove("is-open");
    panel.setAttribute("role", "complementary");
    panel.removeAttribute("aria-modal");
    document.body.classList.remove("filter-panel-open");
    if (main) main.inert = false;
    toolbarTriggers(page).forEach(function (item) { item.setAttribute("aria-expanded", "false"); });

    const duration = ui.openedAt[page] ? Math.round((Date.now() - ui.openedAt[page]) / 1000) : 0;
    root.analytics?.trackEvent?.("Filter Drawer Closed", {
      page,
      source,
      duration: duration < 10 ? "0-9s" : duration < 30 ? "10-29s" : "30s+",
      ui: "adaptive-sheet-v1",
    });

    const focusTarget = ui.lastTrigger;
    if (focusTarget && typeof focusTarget.focus === "function" && focusTarget.isConnected) {
      window.setTimeout(function () { focusTarget.focus(); }, 160);
    }
  }

  const SECTION_LABELS = Object.freeze({
    listed_date: "Listed Date",
    location: "Location",
    subtypes: "Subtypes",
    monthly_rent: "Monthly Rent",
    list_price: "List Price",
    bedrooms: "Bedrooms",
    bathrooms: "Bathrooms",
    pet_policy: "Pet Policy",
  });

  const ACCORDION_DEFAULTS = Object.freeze({
    lease: Object.freeze({
      desktop: Object.freeze([
        "listed_date", "location", "subtypes", "monthly_rent", "bedrooms", "bathrooms",
      ]),
      compact: Object.freeze(["location", "monthly_rent", "bedrooms"]),
    }),
    buy: Object.freeze({
      desktop: Object.freeze([
        "listed_date", "location", "subtypes", "list_price", "bedrooms", "bathrooms",
      ]),
      compact: Object.freeze(["location", "list_price", "bedrooms"]),
    }),
  });

  /**
   * Scroll to and focus a named filter accordion section.
   * @param {ListingPage} page Listing mode containing the accordion.
   * @param {string} [section] Section key to focus.
   * @returns {void}
   */
  function focusSection(page, section) {
    if (!section) return;
    const accordion = document.getElementById(`${page}-options-accordion`);
    const expected = SECTION_LABELS[section];
    if (!accordion || !expected) return;
    window.setTimeout(function () {
      const button = Array.from(accordion.querySelectorAll(".accordion-button")).find(function (item) {
        return String(item.textContent || "").trim() === expected;
      });
      if (!button) return;
      button.scrollIntoView({ behavior: "smooth", block: "start" });
      button.focus({ preventScroll: true });
    }, 220);
  }

  /**
   * Route delegated clicks to open, close, apply, clear, or remove actions.
   * @param {MouseEvent} event Captured document click.
   * @returns {void}
   */
  function clickHandler(event) {
    const openTrigger = event.target.closest("[data-filter-open]");
    if (openTrigger) {
      const page = openTrigger.dataset.filterOpen;
      const group = openTrigger.dataset.filterGroup;
      if (group && openTrigger.classList.contains("map-filter-chip--active")) {
        event.preventDefault();
        removeGroup(page, group);
        return;
      }
      openPanel(page, openTrigger, openTrigger.dataset.filterSection);
      return;
    }

    const clearTrigger = event.target.closest("[data-filter-clear]");
    if (clearTrigger) {
      clearFilters(clearTrigger.dataset.filterClear);
      return;
    }

    const applyTrigger = event.target.closest("[data-filter-apply]");
    if (applyTrigger) {
      const page = applyTrigger.dataset.filterApply;
      closePanel(page, "apply", false);
      return;
    }

    const closeTrigger = event.target.closest("[data-filter-close]");
    if (closeTrigger) {
      closePanel(
        closeTrigger.dataset.filterClose,
        closeTrigger.dataset.filterCloseSource || "dismiss",
        true
      );
    }
  }

  /**
   * Collect visible controls that participate in the panel's focus trap.
   * @param {HTMLElement} panel Open filter panel.
   * @returns {HTMLElement[]} Visible keyboard-focusable descendants.
   */
  function focusableElements(panel) {
    return Array.from(panel.querySelectorAll(
      "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), " +
      "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
    )).filter(function (element) {
      return !element.hidden && element.getClientRects().length > 0;
    });
  }

  /**
   * Handle Escape dismissal and Tab wrapping inside an open panel.
   * @param {KeyboardEvent} event Document keyboard event.
   * @returns {void}
   */
  function keyHandler(event) {
    const page = currentPage();
    const panel = panelFor(page);
    if (!panel || !panel.classList.contains("is-open")) return;

    if (event.key === "Escape") {
      event.preventDefault();
      closePanel(page, "escape", true);
      return;
    }

    if (event.key !== "Tab") return;
    const focusable = focusableElements(panel);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  /**
   * Reset modal-only state when the viewport enters desktop mode.
   * @returns {void}
   */
  function syncBreakpoint() {
    ["lease", "buy"].forEach(function (page) {
      const panel = panelFor(page);
      const main = document.getElementById(`${page}-map-main`);
      if (!panel) return;
      if (window.innerWidth >= DESKTOP_BREAKPOINT) {
        panel.classList.remove("is-open");
        document.getElementById(`${page}-filter-backdrop`)?.classList.remove("is-open");
        panel.setAttribute("role", "complementary");
        panel.removeAttribute("aria-modal");
        if (main) main.inert = false;
      }
    });
    if (window.innerWidth >= DESKTOP_BREAKPOINT) {
      document.body.classList.remove("filter-panel-open");
    }
  }

  /**
   * Attach one-time analytics after the Leaflet map becomes available.
   * @returns {void}
   */
  function attachFirstMapInteraction() {
    const page = currentPage();
    ui.pageStartedAt[page] = ui.pageStartedAt[page] || Date.now();
    let attempts = 0;
    const timer = window.setInterval(function () {
      attempts += 1;
      const map = root.mapGestureControls?.getMap?.();
      if (!map && attempts < 30) return;
      window.clearInterval(timer);
      if (!map || map.__adaptiveFilterAnalyticsBound) return;
      map.__adaptiveFilterAnalyticsBound = true;
      map.once("movestart zoomstart click", function () {
        const seconds = Math.round((Date.now() - ui.pageStartedAt[page]) / 1000);
        root.analytics?.trackEvent?.("First Map Interaction", {
          page,
          elapsed: seconds < 5 ? "0-4s" : seconds < 15 ? "5-14s" : seconds < 45 ? "15-44s" : "45s+",
          ui: "adaptive-sheet-v1",
        });
      });
    }, 300);
  }

  ui.render = render;
  ui.restore = setStateProps;

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
      /**
       * Capture rental controls in Dash callback order and stage or apply them.
       * @returns {Array<*>} Draft and applied values for the callback outputs.
       */
      captureLeaseFilterState: function (
        priceRange, bedroomsRange, bathroomsRange, pets,
        sqftRange, sqftMissing, ppsqftRange, ppsqftMissing,
        parkingRange, parkingMissing, yearRange, yearMissing,
        terms, termsMissing, furnished, furnishedMissing,
        securityRange, securityMissing, petDepositRange, petDepositMissing,
        keyDepositRange, keyDepositMissing, otherDepositRange, otherDepositMissing,
        laundry, laundryMissing, subtypes, listedRange, dateStart, dateEnd,
        dateMissing, downloadRange, uploadRange, ispMissing, rentControl,
        locationText, nearbyZip, zipBoundary, _applyClicks, _viewport, currentApplied
      ) {
        return finalizeCapture("lease", {
          priceRange, bedroomsRange, bathroomsRange, pets,
          sqftRange, sqftMissing, ppsqftRange, ppsqftMissing,
          parkingRange, parkingMissing, yearRange, yearMissing,
          terms, termsMissing, furnished, furnishedMissing,
          securityRange, securityMissing, petDepositRange, petDepositMissing,
          keyDepositRange, keyDepositMissing, otherDepositRange, otherDepositMissing,
          laundry, laundryMissing, subtypes, listedRange, dateStart, dateEnd,
          dateMissing, downloadRange, uploadRange, ispMissing, rentControl,
          locationText, nearbyZip, zipBoundary,
        }, currentApplied);
      },

      /**
       * Capture for-sale controls in Dash callback order and stage or apply them.
       * @returns {Array<*>} Draft and applied values for the callback outputs.
       */
      captureBuyFilterState: function (
        priceRange, bedroomsRange, bathroomsRange,
        sqftRange, sqftMissing, ppsqftRange, ppsqftMissing,
        lotSizeRange, lotSizeMissing, yearRange, yearMissing,
        subtypes, listedRange, dateStart, dateEnd, dateMissing,
        hoaRange, hoaMissing, hoaFrequency,
        downloadRange, uploadRange, ispMissing,
        locationText, nearbyZip, zipBoundary, _applyClicks, _viewport, currentApplied
      ) {
        return finalizeCapture("buy", {
          priceRange, bedroomsRange, bathroomsRange,
          sqftRange, sqftMissing, ppsqftRange, ppsqftMissing,
          lotSizeRange, lotSizeMissing, yearRange, yearMissing,
          subtypes, listedRange, dateStart, dateEnd, dateMissing,
          hoaRange, hoaMissing, hoaFrequency,
          downloadRange, uploadRange, ispMissing,
          locationText, nearbyZip, zipBoundary,
        }, currentApplied);
      },

      /**
       * Preview the number of rentals matching draft values.
       * @param {FilterState} state Draft rental filters.
       * @param {FeatureCollection} fullGeojson Source rental listings.
       * @returns {{count: number | null, updatedAt?: number}} Preview metadata.
       */
      previewLeaseFilterState: function (state, fullGeojson) {
        return preview("lease", state, fullGeojson);
      },
      /**
       * Preview the number of homes matching draft values.
       * @param {FilterState} state Draft for-sale filters.
       * @param {FeatureCollection} fullGeojson Source for-sale listings.
       * @returns {{count: number | null, updatedAt?: number}} Preview metadata.
       */
      previewBuyFilterState: function (state, fullGeojson) {
        return preview("buy", state, fullGeojson);
      },
      /**
       * Apply committed rental filters to the map data.
       * @param {FilterState} state Applied rental filters.
       * @param {FeatureCollection} fullGeojson Source rental listings.
       * @returns {FeatureCollection | *} Filtered data or Dash's no-update value.
       */
      applyLeaseFilterState: function (state, fullGeojson) {
        return apply("lease", state, fullGeojson);
      },
      /**
       * Apply committed for-sale filters to the map data.
       * @param {FilterState} state Applied for-sale filters.
       * @param {FeatureCollection} fullGeojson Source for-sale listings.
       * @returns {FeatureCollection | *} Filtered data or Dash's no-update value.
       */
      applyBuyFilterState: function (state, fullGeojson) {
        return apply("buy", state, fullGeojson);
      },

      /**
       * Apply viewport-specific defaults or add a quick-filter target to the
       * accordion's expanded sections.
       * @returns {string[] | *} Expanded section keys or Dash's no-update value.
       */
      openFilterAccordionSection: function () {
        const args = Array.prototype.slice.call(arguments);
        const current = Array.isArray(args[args.length - 1]) ? args[args.length - 1] : [];
        const id = triggeredIds()[0] || "";
        const page = id.startsWith("buy-") ? "buy" : id.startsWith("lease-") ? "lease" : currentPage();
        if (id === "viewport-listener") {
          const viewportEvent = args[0];
          const isCompact = viewportEvent && typeof viewportEvent["detail.isMobile"] === "boolean"
            ? viewportEvent["detail.isMobile"]
            : window.innerWidth < DESKTOP_BREAKPOINT;
          const mode = isCompact ? "compact" : "desktop";
          ui.accordionModes = ui.accordionModes || {};
          if (ui.accordionModes[page] === mode) return window.dash_clientside.no_update;
          ui.accordionModes[page] = mode;
          return ACCORDION_DEFAULTS[page][mode].slice();
        }
        const button = document.getElementById(id);
        if (button?.classList.contains("map-filter-chip--active")) {
          return window.dash_clientside.no_update;
        }
        const section = button?.dataset.filterSection;
        if (!section) return window.dash_clientside.no_update;
        return current.includes(section) ? current : current.concat(section);
      },
    }),
  });

  // Capture the interaction before Dash's React handlers consume component clicks.
  document.addEventListener("click", clickHandler, true);
  document.addEventListener("keydown", keyHandler);
  window.addEventListener("resize", syncBreakpoint, { passive: true });
  window.addEventListener("orientationchange", syncBreakpoint, { passive: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachFirstMapInteraction, { once: true });
  } else {
    attachFirstMapInteraction();
  }
})();
