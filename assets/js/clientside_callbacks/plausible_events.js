(function () {
    "use strict";

    const root = window.larentals = window.larentals || {};
    const analytics = root.analytics = root.analytics || {};

    const LEASE_FILTER_CATEGORIES = Object.freeze({
        rental_price_slider: "monthly_rent",
        bedrooms_slider: "bedrooms",
        bathrooms_slider: "bathrooms",
        pets_radio: "pet_policy",
        sqft_slider: "sqft",
        sqft_missing_switch: "sqft",
        ppsqft_slider: "price_per_sqft",
        ppsqft_missing_switch: "price_per_sqft",
        garage_spaces_slider: "parking",
        garage_missing_switch: "parking",
        yrbuilt_slider: "year_built",
        yrbuilt_missing_switch: "year_built",
        terms_checklist: "rental_terms",
        terms_missing_switch: "rental_terms",
        furnished_checklist: "furnished",
        furnished_missing_switch: "furnished",
        security_deposit_slider: "deposits",
        security_deposit_missing_switch: "deposits",
        pet_deposit_slider: "deposits",
        pet_deposit_missing_switch: "deposits",
        key_deposit_slider: "deposits",
        key_deposit_missing_switch: "deposits",
        other_deposit_slider: "deposits",
        other_deposit_missing_switch: "deposits",
        laundry_checklist: "laundry",
        laundry_missing_switch: "laundry",
        subtype_checklist: "subtypes",
        listed_date_datepicker_lease: "listed_date",
        listed_date_missing_switch: "listed_date",
        isp_download_speed_slider: "isp_speed",
        isp_upload_speed_slider: "isp_speed",
        isp_speed_missing_switch: "isp_speed",
        rent_control_status: "rent_control",
        "lease-zip-boundary-store": "location",
    });

    const BUY_FILTER_CATEGORIES = Object.freeze({
        list_price_slider: "list_price",
        bedrooms_slider: "bedrooms",
        bathrooms_slider: "bathrooms",
        sqft_slider: "sqft",
        sqft_missing_switch: "sqft",
        ppsqft_slider: "price_per_sqft",
        ppsqft_missing_switch: "price_per_sqft",
        lot_size_slider: "lot_size",
        lot_size_missing_switch: "lot_size",
        yrbuilt_slider: "year_built",
        yrbuilt_missing_switch: "year_built",
        subtype_checklist: "subtypes",
        listed_date_datepicker_buy: "listed_date",
        listed_date_missing_switch: "listed_date",
        hoa_fee_slider: "hoa_fees",
        hoa_fee_missing_switch: "hoa_fees",
        hoa_fee_frequency_checklist: "hoa_fee_frequency",
        isp_download_speed_slider: "isp_speed",
        isp_upload_speed_slider: "isp_speed",
        isp_speed_missing_switch: "isp_speed",
        "buy-zip-boundary-store": "location",
    });

    const SCHOOL_FILTER_NAMES = Object.freeze({
        "search-input": "search",
        "level-dropdown": "special_types",
        "grade-band-checklist": "grade_bands",
        "campus-configuration-dropdown": "grade_span",
        "early-grades-checklist": "early_grades",
        "funding-type-dropdown": "funding_type",
        "enrollment-slider": "enrollment",
        "charter-switch": "charter",
        "magnet-switch": "magnet",
        "title-i-switch": "title_i",
        "recently-opened-switch": "recently_opened",
    });

    const SECTION_LABELS = Object.freeze({
        listed_date: "Listed Date",
        location: "Location",
        subtypes: "Subtypes",
        monthly_rent: "Monthly Rent",
        rent_control: "Rent Control",
        bedrooms: "Bedrooms",
        bathrooms: "Bathrooms",
        pet_policy: "Pet Policy",
        deposits: "Deposits",
        furnished: "Furnished",
        parking_spaces: "Parking Spaces",
        isp_speed: "Internet Service Provider (ISP) Speed",
        laundry: "Laundry",
        ppsqft: "Price Per Sqft",
        rental_terms: "Rental Terms",
        square_footage: "Square Footage",
        year_built: "Year Built",
        list_price: "List Price",
        hoa_fees: "HOA Fees",
        hoa_fee_frequency: "HOA Fee Frequency",
        lot_size: "Lot Size",
    });

    const REPORT_REASONS = new Set([
        "Wrong Location",
        "Unavailable/Sold/Rented",
        "Wrong Details",
        "Incorrect Price",
        "Other",
    ]);

    function trackEvent(name, props, options) {
        if (typeof window.plausible !== "function") return;

        const payload = Object.assign({}, options || {}, { props: props || {} });
        window.plausible(name, payload);
    }

    function currentPage() {
        const path = String(window.location && window.location.pathname || "").toLowerCase();
        return path === "/buy" || path.startsWith("/buy/") ? "buy" : "lease";
    }

    function triggeredComponentIds() {
        const context = window.dash_clientside && window.dash_clientside.callback_context;
        if (!context || !Array.isArray(context.triggered)) return [];

        return Array.from(new Set(context.triggered.map(function (trigger) {
            const propId = String(trigger && trigger.prop_id || "");
            return propId === "." ? "" : propId.split(".")[0];
        }).filter(Boolean)));
    }

    function asStringList(value) {
        if (Array.isArray(value)) return value.map(String);
        if (value === null || value === undefined || value === "") return [];
        return [String(value)];
    }

    function trackFilterChanges(categoryMap) {
        const categories = new Set();
        triggeredComponentIds().forEach(function (componentId) {
            const category = categoryMap[componentId];
            if (category) categories.add(category);
        });
        categories.forEach(function (category) {
            trackEvent("Filter Changed", { category: category });
        });
    }

    analytics.trackEvent = trackEvent;
    analytics.currentPage = currentPage;
    analytics.trackLeaseFilterChanges = function () {
        trackFilterChanges(LEASE_FILTER_CATEGORIES);
    };
    analytics.trackBuyFilterChanges = function () {
        trackFilterChanges(BUY_FILTER_CATEGORIES);
    };
    analytics.trackListingOpened = function () {
        trackEvent("Listing Opened", { page: currentPage() });
    };
    analytics.trackListingLinkClicked = function () {
        trackEvent("Listing Link Clicked", { page: currentPage() });
    };
    analytics.trackReportListingOpened = function () {
        trackEvent("Report Listing Opened", { page: currentPage() });
    };
    analytics.trackReportListingSubmitted = function (reason) {
        const normalizedReason = String(reason || "Other");
        trackEvent("Report Listing Submitted", {
            page: currentPage(),
            reason: REPORT_REASONS.has(normalizedReason) ? normalizedReason : "Other",
        });
    };

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
            trackFilterSectionOpen: function (activeItems, previousData) {
                const current = asStringList(activeItems);
                const previous = asStringList(previousData && previousData.active);
                const previousSet = new Set(previous);

                current.forEach(function (itemId) {
                    if (!previousSet.has(itemId) && SECTION_LABELS[itemId]) {
                        trackEvent("Filter Section Opened", { section: SECTION_LABELS[itemId] });
                    }
                });
                return { active: current };
            },

            trackLayerToggled: function (selectedOverlays, previousData) {
                const current = asStringList(selectedOverlays);
                const previous = asStringList(previousData && previousData.overlays);
                const currentSet = new Set(current);
                const previousSet = new Set(previous);

                current.forEach(function (layerName) {
                    if (!previousSet.has(layerName)) {
                        trackEvent("Layer Toggled", { layer: layerName, action: "on" });
                    }
                });
                previous.forEach(function (layerName) {
                    if (!currentSet.has(layerName)) {
                        trackEvent("Layer Toggled", { layer: layerName, action: "off" });
                    }
                });
                return { overlays: current };
            },

            trackBasemapChanged: function (baseLayerName, previousData) {
                const current = baseLayerName ? String(baseLayerName) : "";
                const previous = previousData && previousData.baseLayer
                    ? String(previousData.baseLayer)
                    : "";

                if (current && previous && current !== previous) {
                    trackEvent("Basemap Changed", { basemap: current });
                }
                return { baseLayer: current };
            },

            trackSchoolFilterChanged: function () {
                const args = Array.prototype.slice.call(arguments);
                const previousData = args[args.length - 1] || {};
                const filterNames = new Set();

                triggeredComponentIds().forEach(function (componentId) {
                    const suffix = componentId.replace(/^(lease|buy)-school-layer-/, "");
                    const filterName = SCHOOL_FILTER_NAMES[suffix];
                    if (filterName) filterNames.add(filterName);
                });
                filterNames.forEach(function (filterName) {
                    trackEvent("School Filter Changed", { filter: filterName });
                });

                return { sequence: Number(previousData.sequence || 0) + 1 };
            },
        }),
    });
})();
