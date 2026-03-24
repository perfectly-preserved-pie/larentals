(function () {
    const EVENT_NAME = "larentals:filter-exclusion-run";
    const STORE_KEY = "__larentalsFilterExclusionRun";
    const SEARCH_INDEX_KEY = "__larentalsFilterExclusionSearchIndex";
    const DEFAULT_VISIBLE_LIMIT = 25; // Max number of excluded listings to keep in memory and show in the panel

    function formatPageLabel(page) {
        if (page === "buy") {
            return "Buy";
        }
        if (page === "lease") {
            return "Lease";
        }
        return "Unknown";
    }

    function getLatestFilterRun() {
        return window[STORE_KEY] || null;
    }

    function getLatestSearchIndex() {
        return window[SEARCH_INDEX_KEY] || {};
    }

    function setLatestSearchIndex(searchIndex) {
        window[SEARCH_INDEX_KEY] = searchIndex || {};
    }

    function normalizeMlsValue(value) {
        if (value === null || value === undefined) {
            return "";
        }

        return String(value)
            .trim()
            .replace(/\.0$/, "")
            .toUpperCase();
    }

    function formatMlsValue(value) {
        const normalizedValue = normalizeMlsValue(value);
        return normalizedValue || "Unknown";
    }

    function publishFilterRun(payload, searchIndex) {
        if (!payload || typeof payload !== "object") {
            return;
        }

        const total = Number(payload.total) || 0;
        const included = Number(payload.included) || 0;
        const excluded = Math.max(
            Number(payload.excluded ?? (total - included)) || 0,
            0,
        );

        const normalizedPayload = {
            page: payload.page || "unknown",
            timestamp: payload.timestamp || new Date().toISOString(),
            total: total,
            included: included,
            excluded: excluded,
            reasonCounts: payload.reasonCounts || {},
            excludedListings: Array.isArray(payload.excludedListings) ? payload.excludedListings : [],
            overflowExcludedCount: Number(payload.overflowExcludedCount) || 0,
        };

        setLatestSearchIndex(searchIndex);
        window[STORE_KEY] = normalizedPayload;
        window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: normalizedPayload }));
    }

    function createRunCollector(page, total) {
        const visibleLimit = DEFAULT_VISIBLE_LIMIT;
        const reasonCounts = {};
        const searchIndex = {};
        const excludedListings = [];
        let excludedCount = 0;

        return {
            capture: function (mlsNumber, failedReasons) {
                if (!Array.isArray(failedReasons) || failedReasons.length === 0) {
                    return;
                }

                excludedCount += 1;

                failedReasons.forEach(function (reason) {
                    reasonCounts[reason] = (reasonCounts[reason] || 0) + 1;
                });

                const listingEntry = {
                    mlsNumber: formatMlsValue(mlsNumber),
                    reasons: failedReasons.slice(),
                };
                const normalizedMls = normalizeMlsValue(mlsNumber);

                if (normalizedMls) {
                    searchIndex[normalizedMls] = listingEntry;
                }

                if (excludedListings.length < visibleLimit) {
                    excludedListings.push(listingEntry);
                }
            },
            publish: function (included) {
                const totalCount = Number(total) || 0;
                const includedCount = Number(included) || 0;

                publishFilterRun({
                    page: page,
                    timestamp: new Date().toISOString(),
                    total: totalCount,
                    included: includedCount,
                    excluded: Math.max(totalCount - includedCount, 0),
                    reasonCounts: reasonCounts,
                    excludedListings: excludedListings,
                    overflowExcludedCount: Math.max(excludedCount - excludedListings.length, 0),
                }, searchIndex);
            },
        };
    }

    function renderSectionTitle(React, text, key) {
        return React.createElement(
            "div",
            {
                key: key,
                style: {
                    fontSize: "11px",
                    fontWeight: 700,
                    letterSpacing: "0.04em",
                    marginBottom: "8px",
                    textTransform: "uppercase",
                },
            },
            text,
        );
    }

    function renderEmptyState(React, text, key) {
        return React.createElement(
            "div",
            {
                key: key,
                style: {
                    color: "#cbd5e1",
                    fontSize: "12px",
                    lineHeight: 1.5,
                },
            },
            text,
        );
    }

    window.LarentalsDevtools = window.LarentalsDevtools || {};
    window.LarentalsDevtools.FilterExclusionPanel = function FilterExclusionPanel(props) {
        const React = window.React;
        const [isOpen, setIsOpen] = React.useState(false);
        const [payload, setPayload] = React.useState(getLatestFilterRun);
        const [searchValue, setSearchValue] = React.useState("");

        React.useEffect(function () {
            function handleFilterRun(event) {
                setPayload(event.detail || null);
                setSearchValue("");
            }

            window.addEventListener(EVENT_NAME, handleFilterRun);
            return function () {
                window.removeEventListener(EVENT_NAME, handleFilterRun);
            };
        }, []);

        const latestPayload = payload || {
            page: "unknown",
            total: 0,
            included: 0,
            excluded: 0,
            reasonCounts: {},
            excludedListings: [],
            timestamp: null,
        };

        const sortedReasons = Object.entries(latestPayload.reasonCounts || {}).sort(function (a, b) {
            return b[1] - a[1];
        });
        const pageLabel = formatPageLabel(latestPayload.page);
        const title = (props && props.title) || "Filter Exclusions";
        const timestampLabel = latestPayload.timestamp
            ? new Date(latestPayload.timestamp).toLocaleTimeString()
            : "Waiting for a filter run";
        const excludedCount = latestPayload.excluded || 0;
        const buttonLabel = title + " (" + excludedCount + ")";
        const normalizedSearchValue = normalizeMlsValue(searchValue);
        const matchedListing = normalizedSearchValue
            ? getLatestSearchIndex()[normalizedSearchValue] || null
            : null;
        const visibleListings = normalizedSearchValue
            ? (matchedListing ? [matchedListing] : [])
            : latestPayload.excludedListings;

        const buttonStyle = {
            appearance: "none",
            background: excludedCount > 0 ? "#7f1d1d" : "#1f2937",
            border: "1px solid " + (excludedCount > 0 ? "#ef4444" : "#475569"),
            borderRadius: "6px",
            color: "#f8fafc",
            cursor: "pointer",
            fontSize: "12px",
            fontWeight: 600,
            lineHeight: 1.2,
            padding: "6px 10px",
        };

        const overlay = isOpen ? React.createElement(
            "div",
            {
                key: "overlay",
                style: {
                    position: "fixed",
                    right: "20px",
                    bottom: "64px",
                    width: "380px",
                    maxWidth: "calc(100vw - 24px)",
                    maxHeight: "60vh",
                    overflowY: "auto",
                    background: "#0f172a",
                    border: "1px solid #334155",
                    borderRadius: "10px",
                    boxShadow: "0 16px 40px rgba(15, 23, 42, 0.4)",
                    color: "#f8fafc",
                    padding: "14px",
                    zIndex: 9999,
                },
            },
            [
                React.createElement(
                    "div",
                    {
                        key: "header",
                        style: {
                            alignItems: "center",
                            display: "flex",
                            justifyContent: "space-between",
                            marginBottom: "12px",
                        },
                    },
                    [
                        React.createElement(
                            "div",
                            { key: "header-copy" },
                            [
                                React.createElement(
                                    "div",
                                    {
                                        key: "title",
                                        style: {
                                            fontSize: "14px",
                                            fontWeight: 700,
                                            marginBottom: "2px",
                                        },
                                    },
                                    pageLabel + " filter run",
                                ),
                                React.createElement(
                                    "div",
                                    {
                                        key: "timestamp",
                                        style: {
                                            color: "#cbd5e1",
                                            fontSize: "12px",
                                        },
                                    },
                                    timestampLabel,
                                ),
                            ],
                        ),
                        React.createElement(
                            "button",
                            {
                                key: "close",
                                onClick: function () {
                                    setIsOpen(false);
                                },
                                style: {
                                    appearance: "none",
                                    background: "transparent",
                                    border: "none",
                                    color: "#cbd5e1",
                                    cursor: "pointer",
                                    fontSize: "16px",
                                    lineHeight: 1,
                                    padding: 0,
                                },
                                type: "button",
                            },
                            "x",
                        ),
                    ],
                ),
                React.createElement(
                    "div",
                    {
                        key: "summary",
                        style: {
                            background: "#111827",
                            borderRadius: "8px",
                            marginBottom: "14px",
                            padding: "10px 12px",
                        },
                    },
                    [
                        React.createElement(
                            "div",
                            {
                                key: "summary-total",
                                style: { fontSize: "12px", marginBottom: "4px" },
                            },
                            "Included " + latestPayload.included + " of " + latestPayload.total + " listings",
                        ),
                        React.createElement(
                            "div",
                            {
                                key: "summary-excluded",
                                style: {
                                    color: excludedCount > 0 ? "#fca5a5" : "#93c5fd",
                                    fontSize: "13px",
                                    fontWeight: 700,
                                },
                            },
                            "Excluded " + excludedCount + " listings",
                        ),
                    ],
                ),
                renderSectionTitle(React, "Failed Filters (Reasons)", "reasons-title"),
                sortedReasons.length
                    ? React.createElement(
                        "div",
                        {
                            key: "reasons",
                            style: {
                                display: "grid",
                                gap: "6px",
                                marginBottom: "14px",
                            },
                        },
                        sortedReasons.map(function (entry) {
                            return React.createElement(
                                "div",
                                {
                                    key: "reason-" + entry[0],
                                    style: {
                                        alignItems: "center",
                                        background: "#111827",
                                        borderRadius: "8px",
                                        display: "flex",
                                        fontSize: "12px",
                                        justifyContent: "space-between",
                                        padding: "8px 10px",
                                    },
                                },
                                [
                                    React.createElement("span", { key: "label" }, entry[0]),
                                    React.createElement(
                                        "span",
                                        {
                                            key: "count",
                                            style: {
                                                color: "#93c5fd",
                                                fontVariantNumeric: "tabular-nums",
                                                fontWeight: 700,
                                            },
                                        },
                                        entry[1],
                                    ),
                                ],
                            );
                        }),
                    )
                    : renderEmptyState(React, "No listings were excluded on the latest run.", "reasons-empty"),
                renderSectionTitle(React, "Excluded Listings", "listings-title"),
                React.createElement(
                    "input",
                    {
                        key: "search",
                        onChange: function (event) {
                            setSearchValue(event.target.value || "");
                        },
                        placeholder: "Search exact MLS number",
                        style: {
                            appearance: "none",
                            background: "#111827",
                            border: "1px solid #334155",
                            borderRadius: "8px",
                            color: "#f8fafc",
                            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                            fontSize: "12px",
                            marginBottom: "10px",
                            outline: "none",
                            padding: "10px 12px",
                            width: "100%",
                        },
                        type: "text",
                        value: searchValue,
                    },
                ),
                React.createElement(
                    "div",
                    {
                        key: "results-count",
                        style: {
                            color: "#94a3b8",
                            fontSize: "11px",
                            marginBottom: "10px",
                        },
                    },
                    normalizedSearchValue
                        ? (matchedListing
                            ? "Showing exact match for MLS " + matchedListing.mlsNumber
                            : "No excluded listing found for MLS " + searchValue.trim())
                        : "Showing " + latestPayload.excludedListings.length + " excluded listings"
                            + (latestPayload.overflowExcludedCount
                                ? " plus " + latestPayload.overflowExcludedCount + " more searchable by MLS"
                                : ""),
                ),
                visibleListings.length
                    ? React.createElement(
                        "div",
                        {
                            key: "listings",
                            style: {
                                display: "grid",
                                gap: "8px",
                            },
                        },
                        visibleListings.map(function (listing, index) {
                            return React.createElement(
                                "div",
                                {
                                    key: "listing-" + listing.mlsNumber + "-" + index,
                                    style: {
                                        background: "#111827",
                                        borderRadius: "8px",
                                        padding: "10px 12px",
                                    },
                                },
                                [
                                    React.createElement(
                                        "div",
                                        {
                                            key: "mls",
                                            style: {
                                                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                                                fontSize: "12px",
                                                fontWeight: 700,
                                                marginBottom: "4px",
                                            },
                                        },
                                        "MLS " + listing.mlsNumber,
                                    ),
                                    React.createElement(
                                        "div",
                                        {
                                            key: "reasons",
                                            style: {
                                                color: "#cbd5e1",
                                                fontSize: "12px",
                                                lineHeight: 1.5,
                                            },
                                        },
                                        listing.reasons.join(", "),
                                    ),
                                ],
                            );
                        }),
                    )
                    : renderEmptyState(
                        React,
                        normalizedSearchValue
                            ? "No excluded listing matched that exact MLS number."
                            : "No excluded listings captured yet.",
                        "listings-empty",
                    ),
            ],
        ) : null;

        return React.createElement(
            React.Fragment,
            null,
            [
                React.createElement(
                    "button",
                    {
                        key: "toggle",
                        onClick: function () {
                            setIsOpen(!isOpen);
                        },
                        style: buttonStyle,
                        type: "button",
                    },
                    buttonLabel,
                ),
                overlay,
            ],
        );
    };

    window.larentals = window.larentals || {};
    window.larentals.filterDevtools = Object.assign(
        {},
        window.larentals.filterDevtools,
        {
            createRunCollector: createRunCollector,
            getLatestFilterRun: getLatestFilterRun,
            publishFilterRun: publishFilterRun,
        },
    );
})();
