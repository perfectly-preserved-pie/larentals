(function () {
    "use strict";

    const cache = new Map();
    let dialog;
    let drawerSequence = 0;
    const statusLabels = {
        unavailable: "Records are temporarily unavailable. Please try again shortly.",
        outside_coverage: "ZIMAS and LA City permits cover the City of Los Angeles. This listing is outside that coverage.",
        unmatched: "We could not confidently match this address to one LA City parcel.",
        missing_location: "A verified listing location is not available.",
        not_cached: "Records for this property have not been prepared yet. They will appear after the next server refresh.",
    };

    /**
     * Escape source fields before inserting records into popup or drawer HTML.
     * Official descriptions can contain markup and must remain display text.
     * @param {unknown} raw Source text.
     * @returns {string} HTML-safe text.
     */
    function escapeHtml(raw) {
        return String(raw ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
    }

    /**
     * Render an external source link only when it has an HTTPS destination.
     * Rejected links leave readable text, keeping malformed source URLs inert.
     * @param {unknown} raw URL from the property API.
     * @param {string} label Visible link description.
     * @returns {string} Safe anchor or escaped text.
     */
    function sourceLink(raw, label) {
        try {
            const url = new URL(String(raw));
            if (url.protocol === "https:") {
                return `<a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
            }
        } catch (_) { /* A missing source still has a readable label. */ }
        return escapeHtml(label);
    }

    /**
     * Build a same-origin endpoint for a listing, respecting Dash mounts.
     * The market is fixed by the popup rather than accepting a remote URL.
     * @param {string} market Buy or lease page key.
     * @param {string} id Stored MLS identifier.
     * @returns {string} Property-context request URL.
     */
    function endpoint(market, id) {
        const cfg = window.__dash_config || {};
        const prefix = String(cfg.requests_pathname_prefix || cfg.url_base_pathname || "/").replace(/\/$/, "");
        return `${prefix}/api/${market === "buy" ? "buy" : "lease"}/property-context/${encodeURIComponent(id)}`;
    }

    /**
     * Share saved server records between popup summaries and the drawer.
     * Short browser lifetimes let newly published snapshots appear promptly;
     * these requests never initiate an agency lookup on the server.
     * @param {string} market Buy or lease page key.
     * @param {string} id Stored MLS identifier.
     * @returns {Promise<object>} Official property context.
     */
    function fetchContext(market, id) {
        const key = endpoint(market, id);
        const entry = cache.get(key);
        if (entry && entry.expires > Date.now()) return entry.promise;
        const next = { expires: Infinity, promise: null };
        next.promise = fetch(key, { credentials: "same-origin", headers: { Accept: "application/json" }, signal: AbortSignal.timeout(10000) })
            .then(response => {
                if (!response.ok) throw new Error("Property records unavailable");
                return response.json();
            })
            .then(context => {
                next.expires = Date.now() + 60000;
                return context;
            })
            .catch(error => { cache.delete(key); throw error; });
        if (cache.size >= 128) cache.delete(cache.keys().next().value);
        cache.set(key, next);
        return next.promise;
    }

    /**
     * Reserve space for independently loaded hazard details in each popup.
     * Listings stay usable while official services respond or are unavailable.
     * @param {object} listing Popup listing fields.
     * @param {string} market Buy or lease page key.
     * @returns {string} Summary container with a persistent drawer button.
     */
    function placeholder(listing, market) {
        const id = String(listing.mls_number ?? "").trim().replace(/\.0$/, "");
        if (!id) return "";
        return `<section class="property-context-summary" data-property-market="${escapeHtml(market)}" data-property-id="${escapeHtml(id)}">
            <strong>${market === "buy" ? "Property & hazards" : "Hazards & property records"}</strong>
            <div class="property-context-summary__facts" aria-live="polite">Loading saved records…</div>
            <button type="button" class="property-context-open">View property records</button>
        </section>`;
    }

    /**
     * Summarize a designation without treating missing map coverage as safe.
     * Full flood subtypes and fire responsibility areas stay in the drawer.
     * @param {object} context Official property context.
     * @param {string} market Buy or lease page key.
     * @returns {string} Compact hazard and buyer zoning rows.
     */
    function summaryFacts(context, market) {
        const fire = context.fire || {};
        const flood = context.flood || {};
        const zimas = context.zimas || {};
        const fireLabel = fire.status === "available" ? fire.zones.map(zone => zone.designation).join(" / ")
            : fire.status === "no_intersection" ? "No mapped zone at listing point" : "Not available";
        const floodLabel = flood.status === "available" ? flood.zones.map(zone => `${zone.zone}${zone.subtype ? ` · ${zone.subtype}` : ""}`).join(" / ")
            : flood.status === "no_intersection" ? "No flood zone returned" : "Not available";
        const zoning = (zimas.planning || []).filter(row => row.label === "Zoning").map(row => row.value).join(" / ");
        return `<dl><div><dt>Fire hazard severity</dt><dd>${escapeHtml(fireLabel)}</dd></div>
            <div><dt>FEMA flood zone</dt><dd>${escapeHtml(floodLabel)}</dd></div>
            ${market === "buy" ? `<div><dt>Zoning</dt><dd>${escapeHtml(zoning || (zimas.status === "outside_coverage" ? "Outside LA City coverage" : "Not available"))}</dd></div>` : ""}</dl>`;
    }

    /**
     * Hydrate only summary containers that still belong to the open popup.
     * Detached nodes are ignored so a slow response cannot overwrite a new home.
     * @param {HTMLElement} popup Open Leaflet popup element.
     * @returns {void}
     */
    function hydratePopup(popup) {
        popup.querySelectorAll(".property-context-summary").forEach(container => {
            if (container.dataset.propertyLoading) return;
            container.dataset.propertyLoading = "true";
            const { propertyMarket: market, propertyId: id } = container.dataset;
            fetchContext(market, id).then(context => {
                if (!container.isConnected) return;
                container.querySelector(".property-context-summary__facts").innerHTML = summaryFacts(context, market);
            }).catch(() => {
                if (container.isConnected) container.querySelector(".property-context-summary__facts").textContent = "Official records are temporarily unavailable.";
            });
        });
    }

    /**
     * Render source rows as text with optional official drill-through links.
     * Repeated labels remain separate, preserving notes for multi-unit parcels.
     * @param {Array<object>} rows Official label, value, and URL fields.
     * @returns {string} Definition list or explicit missing-data message.
     */
    function recordRows(rows) {
        if (!rows?.length) return '<p class="property-records-note">No information returned in this section.</p>';
        return `<dl class="property-records-fields">${rows.map(row => `<div><dt>${escapeHtml(row.label)}</dt>
            <dd>${row.url ? sourceLink(row.url, row.value) : escapeHtml(row.value)}</dd></div>`).join("")}</dl>`;
    }

    /**
     * Build an expandable drawer section with an audience-specific default.
     * Native details controls keep long parcel reports navigable by keyboard.
     * @param {string} title Section title.
     * @param {string} content Already escaped section HTML.
     * @param {boolean} open Whether the section starts expanded.
     * @returns {string} Accessible section markup.
     */
    function section(title, content, open = false) {
        return `<details class="property-records-section" ${open ? "open" : ""}><summary>${escapeHtml(title)}</summary><div>${content}</div></details>`;
    }

    /**
     * Label a saved source check separately from the agency's publication date.
     * Old successful records stay visible after a failed refresh, with their
     * original check time and an indication that they await an update.
     * @param {object} source Saved source section.
     * @returns {string} Snapshot freshness note or an empty string.
     */
    function snapshotNote(source) {
        if (!source?.checked_at) return "";
        const checked = new Date(source.checked_at);
        if (Number.isNaN(checked.getTime())) return "";
        return `<p class="property-records-note">Saved records checked ${escapeHtml(checked.toLocaleString())}.${source.refresh_failed || source.stale ? " An update is pending; the last saved records are shown." : ""}</p>`;
    }

    /**
     * Describe point-based hazards alongside separately sourced ZIMAS flags.
     * A ZIMAS very-high yes/no flag cannot replace the newer three-level fire
     * designation, and both sources remain visible when they differ.
     * @param {object} context Property context with independent source statuses.
     * @returns {string} Hazard records and their practical limits.
     */
    function hazardDetails(context) {
        const fire = context.fire || {};
        const flood = context.flood || {};
        const fireRows = (fire.zones || []).map(zone => ({ label: zone.responsibility, value: zone.designation }));
        const floodRows = (flood.zones || []).map(zone => ({ label: `FEMA zone ${zone.zone}`, value: [zone.subtype,
            zone.special_flood_hazard_area === "T" ? "Special Flood Hazard Area" : zone.special_flood_hazard_area === "F" ? "Outside Special Flood Hazard Area" : ""].filter(Boolean).join(" · ") || "Subtype not reported" }));
        return `<h3>Fire hazard severity</h3>${snapshotNote(fire)}${fire.status === "available" ? recordRows(fireRows) : `<p>${escapeHtml(fire.status === "no_intersection" ? "No mapped fire zone intersects the listing point." : statusLabels[fire.status] || "Not available")}</p>`}
            <p class="property-records-note">${sourceLink(fire.source_url, "CAL FIRE maps")}. LRA designations are state recommendations; check local adoption. Hazard designations do not measure an individual building's fire risk or insurance cost.</p>
            <h3>Flood zone</h3>${snapshotNote(flood)}${flood.status === "available" ? recordRows(floodRows) : `<p>${escapeHtml(flood.status === "no_intersection" ? "FEMA did not return a mapped flood zone for this location." : statusLabels[flood.status] || "Not available")}</p>`}
            <p class="property-records-note">${sourceLink(flood.source_url, "FEMA Flood Map Service Center")}. Flooding can occur outside mapped high-hazard areas. These map lookups use the listing point; they do not evaluate the whole parcel.</p>
            <h3>ZIMAS parcel hazard flags</h3>${snapshotNote(context.zimas)}${context.zimas?.status === "available" ? recordRows(context.zimas.hazards) : `<p>${escapeHtml(statusLabels[context.zimas?.status] || "Not available")}</p>`}
            <p class="property-records-note">Liquefaction, landslide, and fault zones describe mapped ground hazards, not a building's earthquake performance. ${sourceLink("https://www.conservation.ca.gov/cgs/geohazards/eq-zapp", "Check California earthquake hazard maps")}.</p>`;
    }

    /**
     * Show issued building permit history with its recorded status and dates.
     * A capped list is labeled as recent records and cannot establish whether
     * every alteration was permitted or completed.
     * @param {object} permits Permit section from the property API.
     * @returns {string} Permit cards, source attribution, and coverage notes.
     */
    function permitDetails(permits) {
        let content = snapshotNote(permits);
        if (permits.status !== "available") {
            content += `<p>${escapeHtml(statusLabels[permits.status] || "Not available")}</p>`;
        } else if (!permits.records?.length) {
            content += "<p>No matching issued building permits were returned from the 2020–present dataset.</p>";
        } else {
            content += `<ol class="property-permits">${permits.records.map(row => `<li>
                <strong>${escapeHtml(row.permit_type || "Building permit")} · ${escapeHtml(row.permit_nbr)}</strong>
                <p>${escapeHtml(row.work_desc || "Work description not supplied")}</p>
                <dl><div><dt>Issued</dt><dd>${escapeHtml(row.issue_date?.slice(0, 10) || "Not reported")}</dd></div>
                <div><dt>Recorded status</dt><dd>${escapeHtml(row.status_desc || "Not reported")}</dd></div>
                <div><dt>Status date</dt><dd>${escapeHtml(row.status_date?.slice(0, 10) || "Not reported")}</dd></div>
                ${row.refresh_time ? `<div><dt>Source refreshed</dt><dd>${escapeHtml(row.refresh_time.slice(0, 10))}</dd></div>` : ""}</dl>
                <p class="property-records-note">${escapeHtml(row.primary_address || "")}</p></li>`).join("")}</ol>`;
            if (permits.has_more) content += "<p>Showing the 25 most recently issued permits; more records are available at the source.</p>";
        }
        return `${content}<p class="property-records-note">${sourceLink(permits.source_url, "LA City issued building permits, 2020–present")}. Records apply to the matched parcel and may cover other units. An issued permit does not establish completed work or passed final inspections. Electrical, mechanical, older records, and pending applications may require ${sourceLink("https://dbs.lacity.gov/services", "LADBS permit and inspection records")}.</p>`;
    }

    /**
     * Order parcel details around the decision each audience is making.
     * Renters see reported housing protections first; buyers see hazards,
     * zoning restrictions, and permits before the housing and planning history.
     * @param {object} context Official property context.
     * @param {string} market Buy or lease page key.
     * @returns {string} Drawer body containing source links and check time.
     */
    function drawerContent(context, market) {
        const zimas = context.zimas || {};
        if (["fire", "flood", "zimas", "permits"].every(name => context[name]?.status === "not_cached")) {
            return `<p class="property-records-address">${escapeHtml(context.address)}</p><p>${escapeHtml(statusLabels.not_cached)}</p>
                <p>${sourceLink(zimas.source_url, "Look up this property in ZIMAS")}</p>`;
        }
        const unavailable = `<p>${escapeHtml(statusLabels[zimas.status] || "Not available")}</p>`;
        const housing = section("Housing & tenant protections", (zimas.status === "available" ? recordRows(zimas.housing) : unavailable)
            + '<p class="property-records-note">City records describe the property. Coverage may differ by unit or tenancy; use the source notes and LAHD records to investigate.</p>', market === "lease");
        const hazards = section("Mapped hazards", hazardDetails(context), true);
        const planning = section("Zoning & renovation restrictions", (zimas.status === "available" ? recordRows(zimas.planning) : unavailable)
            + '<p class="property-records-note">Zone strings and overlays are shown as reported. They are a starting point for researching a project, rather than confirmation that an ADU, addition, or redevelopment will be approved.</p>', market === "buy");
        const permits = section("Building permit history", permitDetails(context.permits || {}), market === "buy");
        const cases = section("Planning cases & recorded activity", (zimas.status === "available" ? recordRows(zimas.cases) : unavailable)
            + '<p class="property-records-note">These are records attached to this property, including historical cases and ordinances. A listed case does not establish approval, construction, or nearby construction activity.</p>');
        const checked = context.checked_at ? new Date(context.checked_at) : null;
        return `<p class="property-records-address">${escapeHtml(context.address)}</p>
            ${zimas.address ? `<p class="property-records-note">City records matched to ${escapeHtml(zimas.address)}.</p>` : ""}
            <p class="property-records-note">${sourceLink(zimas.source_url, "Open ZIMAS")}${zimas.pin ? ` · PIN ${escapeHtml(zimas.pin)}` : ""}
            ${zimas.apns?.length ? ` · APN ${escapeHtml(zimas.apns.join(", "))}` : ""}<br>
            ${!checked || Number.isNaN(checked.getTime()) ? "" : `Records checked ${escapeHtml(checked.toLocaleString())}`}</p>
            ${market === "lease" ? housing + hazards + permits + planning + cases : hazards + planning + permits + housing + cases}`;
    }

    /**
     * Create one native modal drawer shared by both listing pages.
     * The dialog provides focus containment, Escape dismissal, and return focus
     * without adding Leaflet's generated markup to the Dash component tree.
     * @returns {HTMLDialogElement} Mounted records drawer.
     */
    function ensureDialog() {
        if (dialog?.isConnected) return dialog;
        dialog = document.createElement("dialog");
        dialog.className = "property-records-drawer";
        dialog.setAttribute("aria-labelledby", "property-records-title");
        dialog.innerHTML = '<header><h2 id="property-records-title">Property records & hazards</h2><button type="button" class="property-records-close" aria-label="Close property records">×</button></header><div class="property-records-body" aria-live="polite"></div>';
        dialog.querySelector(".property-records-close").addEventListener("click", () => dialog.close());
        dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
        dialog.addEventListener("close", () => { drawerSequence += 1; });
        document.body.append(dialog);
        return dialog;
    }

    /**
     * Open the records drawer for the clicked popup's listing identity.
     * A sequence guard prevents late responses from replacing another home's
     * records after the user closes or switches the drawer.
     * @param {MouseEvent} event Delegated popup button click.
     * @returns {void}
     */
    function handleOpen(event) {
        const button = event.target?.closest?.(".property-context-open");
        if (!button) return;
        const container = button.closest(".property-context-summary");
        if (!container) return;
        event.preventDefault();
        event.stopPropagation();
        const { propertyMarket: market, propertyId: id } = container.dataset;
        const drawer = ensureDialog();
        const body = drawer.querySelector(".property-records-body");
        const sequence = ++drawerSequence;
        body.innerHTML = '<p role="status">Loading official property records…</p>';
        if (!drawer.open) drawer.showModal();
        fetchContext(market, id).then(context => {
            if (sequence === drawerSequence && drawer.open) body.innerHTML = drawerContent(context, market);
        }).catch(() => {
            if (sequence === drawerSequence && drawer.open) body.innerHTML = '<p role="status">Official records could not be loaded. Close this panel and try again shortly.</p>';
        });
    }

    document.addEventListener("click", handleOpen, true);
    window.larentals = window.larentals || {};
    window.larentals.propertyContext = { placeholder, hydratePopup };
})();
