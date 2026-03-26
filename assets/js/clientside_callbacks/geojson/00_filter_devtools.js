(function () {
    const EVENT_NAME = "larentals:filter-exclusion-run";
    const STORE_KEY = "__larentalsFilterExclusionRun";
    const SEARCH_INDEX_KEY = "__larentalsFilterExclusionSearchIndex";
    const DEFAULT_VISIBLE_LIMIT = 25; // Max number of excluded listings to keep in memory and show in the panel
    const REASON_PROPERTY_MAP = {
        buy: {
            "Price": ["list_price"],
            "Bedrooms": ["bedrooms"],
            "Bathrooms": ["total_bathrooms"],
            "Sqft": ["sqft"],
            "Price per sqft": ["ppsqft"],
            "Lot size": ["lot_size"],
            "Year built": ["year_built"],
            "Subtype": ["subtype"],
            "Listed date": ["listed_date"],
            "HOA fee": ["hoa_fee"],
            "HOA frequency": ["hoa_fee_frequency"],
            "Download speed": ["best_dn"],
            "Upload speed": ["best_up"],
            "ZIP boundary": [],
        },
        lease: {
            "Price": ["list_price"],
            "Bedrooms": ["bedrooms"],
            "Bathrooms": ["total_bathrooms"],
            "Pet policy": ["pet_policy"],
            "Sqft": ["sqft"],
            "Price per sqft": ["ppsqft"],
            "Parking": ["parking_spaces"],
            "Year built": ["year_built"],
            "Lease terms": ["terms"],
            "Furnished": ["furnished"],
            "Security deposit": ["security_deposit"],
            "Pet deposit": ["pet_deposit"],
            "Key deposit": ["key_deposit"],
            "Other deposit": ["other_deposit"],
            "Laundry": ["laundry_category"],
            "Subtype": ["subtype"],
            "Listed date": ["listed_date"],
            "Download speed": ["best_dn"],
            "Upload speed": ["best_up"],
            "ZIP boundary": [],
        },
    };

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

    function cloneProperties(properties) {
        if (!properties || typeof properties !== "object" || Array.isArray(properties)) {
            return {};
        }

        return Object.assign({}, properties);
    }

    function formatPropertyLabel(key) {
        return String(key || "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, function (char) {
                return char.toUpperCase();
            });
    }

    function formatPropertyValue(value) {
        if (value === null || value === undefined || value === "") {
            return "None";
        }

        if (typeof value === "object") {
            try {
                return JSON.stringify(value);
            } catch (_error) {
                return String(value);
            }
        }

        return String(value);
    }

    function getHighlightedPropertyKeys(page, reasons) {
        const pageMap = REASON_PROPERTY_MAP[page] || {};
        const keys = new Set();

        (reasons || []).forEach(function (reason) {
            (pageMap[reason] || []).forEach(function (propertyKey) {
                keys.add(propertyKey);
            });
        });

        return keys;
    }

    function buildListingEntry(page, mlsNumber, failedReasons, properties) {
        return {
            page: page,
            mlsNumber: formatMlsValue(mlsNumber),
            reasons: failedReasons.slice(),
            properties: cloneProperties(properties),
        };
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
            capture: function (mlsNumber, failedReasons, properties) {
                if (!Array.isArray(failedReasons) || failedReasons.length === 0) {
                    return;
                }

                excludedCount += 1;

                failedReasons.forEach(function (reason) {
                    reasonCounts[reason] = (reasonCounts[reason] || 0) + 1;
                });

                const listingEntry = buildListingEntry(page, mlsNumber, failedReasons, properties);
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
        const [selectedListingMls, setSelectedListingMls] = React.useState("");

        React.useEffect(function () {
            function handleFilterRun(event) {
                setPayload(event.detail || null);
                setSearchValue("");
                setSelectedListingMls("");
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
        const searchIndex = getLatestSearchIndex();
        const matchedListing = normalizedSearchValue
            ? searchIndex[normalizedSearchValue] || null
            : null;
        const visibleListings = normalizedSearchValue
            ? (matchedListing ? [matchedListing] : [])
            : latestPayload.excludedListings;
        const normalizedSelectedListingMls = normalizeMlsValue(selectedListingMls);
        const selectedListing = normalizedSelectedListingMls
            ? searchIndex[normalizedSelectedListingMls] || null
            : null;
        const highlightedPropertyKeys = selectedListing
            ? getHighlightedPropertyKeys(selectedListing.page || latestPayload.page, selectedListing.reasons)
            : new Set();
        const selectedPropertyEntries = selectedListing
            ? Object.entries(selectedListing.properties || {}).sort(function (a, b) {
                const aHighlighted = highlightedPropertyKeys.has(a[0]) ? 0 : 1;
                const bHighlighted = highlightedPropertyKeys.has(b[0]) ? 0 : 1;

                if (aHighlighted !== bHighlighted) {
                    return aHighlighted - bHighlighted;
                }

                return a[0].localeCompare(b[0]);
            })
            : [];

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
                            const isSelected = normalizeMlsValue(listing.mlsNumber) === normalizedSelectedListingMls;

                            return React.createElement(
                                "div",
                                {
                                    key: "listing-" + listing.mlsNumber + "-" + index,
                                    style: {
                                        background: isSelected ? "#1e293b" : "#111827",
                                        border: "1px solid " + (
                                            isSelected
                                                ? "#60a5fa"
                                                : "#334155"
                                        ),
                                        borderRadius: "8px",
                                        padding: "10px 12px",
                                    },
                                },
                                [
                                    React.createElement(
                                        "button",
                                        {
                                            key: "listing-toggle",
                                            onClick: function () {
                                                setSelectedListingMls(isSelected ? "" : listing.mlsNumber);
                                            },
                                            style: {
                                                appearance: "none",
                                                background: "transparent",
                                                border: "none",
                                                color: "inherit",
                                                cursor: "pointer",
                                                display: "block",
                                                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                                                fontSize: "12px",
                                                fontWeight: 700,
                                                marginBottom: "4px",
                                                padding: 0,
                                                textAlign: "left",
                                                width: "100%",
                                            },
                                            type: "button",
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
                                    isSelected && selectedListing
                                        ? React.createElement(
                                            "div",
                                            {
                                                key: "selected-inline",
                                                style: {
                                                    borderTop: "1px solid #334155",
                                                    marginTop: "10px",
                                                    paddingTop: "10px",
                                                },
                                            },
                                            [
                                                React.createElement(
                                                    "div",
                                                    {
                                                        key: "selected-copy",
                                                        style: {
                                                            color: "#94a3b8",
                                                            fontSize: "11px",
                                                            marginBottom: "10px",
                                                        },
                                                    },
                                                    "Highlighted fields correspond to failed filters.",
                                                ),
                                                React.createElement(
                                                    "div",
                                                    {
                                                        key: "selected-reasons",
                                                        style: {
                                                            display: "flex",
                                                            flexWrap: "wrap",
                                                            gap: "6px",
                                                            marginBottom: "12px",
                                                        },
                                                    },
                                                    (selectedListing.reasons || []).map(function (reason) {
                                                        return React.createElement(
                                                            "span",
                                                            {
                                                                key: "reason-pill-" + reason,
                                                                style: {
                                                                    background: "#7f1d1d",
                                                                    border: "1px solid #ef4444",
                                                                    borderRadius: "999px",
                                                                    color: "#fecaca",
                                                                    fontSize: "11px",
                                                                    padding: "4px 8px",
                                                                },
                                                            },
                                                            reason,
                                                        );
                                                    }),
                                                ),
                                                React.createElement(
                                                    "div",
                                                    {
                                                        key: "properties",
                                                        style: {
                                                            display: "grid",
                                                            gap: "6px",
                                                            maxHeight: "260px",
                                                            overflowY: "auto",
                                                        },
                                                    },
                                                    selectedPropertyEntries.map(function (entry) {
                                                        const propertyKey = entry[0];
                                                        const propertyValue = entry[1];
                                                        const isHighlighted = highlightedPropertyKeys.has(propertyKey);

                                                        return React.createElement(
                                                            "div",
                                                            {
                                                                key: "property-" + propertyKey,
                                                                style: {
                                                                    background: isHighlighted ? "#3f1d1d" : "#0f172a",
                                                                    border: "1px solid " + (isHighlighted ? "#ef4444" : "#334155"),
                                                                    borderRadius: "8px",
                                                                    padding: "8px 10px",
                                                                },
                                                            },
                                                            [
                                                                React.createElement(
                                                                    "div",
                                                                    {
                                                                        key: "property-label",
                                                                        style: {
                                                                            color: isHighlighted ? "#fecaca" : "#93c5fd",
                                                                            fontSize: "11px",
                                                                            fontWeight: 700,
                                                                            marginBottom: "3px",
                                                                            textTransform: "none",
                                                                        },
                                                                    },
                                                                    formatPropertyLabel(propertyKey),
                                                                ),
                                                                React.createElement(
                                                                    "div",
                                                                    {
                                                                        key: "property-value",
                                                                        style: {
                                                                            color: "#f8fafc",
                                                                            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                                                                            fontSize: "11px",
                                                                            lineHeight: 1.45,
                                                                            overflowWrap: "anywhere",
                                                                            whiteSpace: "pre-wrap",
                                                                        },
                                                                    },
                                                                    formatPropertyValue(propertyValue),
                                                                ),
                                                            ],
                                                        );
                                                    }),
                                                ),
                                            ],
                                        )
                                        : null,
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
