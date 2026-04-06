(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupUtils = popupApi && popupApi.utils;
    const popupRuntime = popupApi && popupApi.runtime;
    const registerPopupBuilder = popupRuntime && popupRuntime.registerPopupBuilder;

    if (!popupUtils || typeof registerPopupBuilder !== "function") {
        console.error("Additional layer popup utils did not load before the schools popup builder.");
        return;
    }

    const buildExternalLink = popupUtils.buildExternalLink;
    const escapeHtml = popupUtils.escapeHtml;
    const formatTextValue = popupUtils.formatTextValue;
    const getTrimmedString = popupUtils.getTrimmedString;
    const renderPopupCard = popupUtils.renderPopupCard;

    /**
     * Format a percentage value for popup display.
     *
     * @param {unknown} value Raw percentage value.
     * @returns {string} Percent label or `N/A`.
     */
    function formatPct(value) {
        const numberValue = Number(value);
        if (!Number.isFinite(numberValue)) {
            return "N/A";
        }
        return `${numberValue.toFixed(1)}%`;
    }

    /**
     * Format an enrollment value for popup display.
     *
     * @param {unknown} value Raw enrollment count.
     * @returns {string} Formatted count or `N/A`.
     */
    function formatEnrollment(value) {
        const numberValue = Number(value);
        if (!Number.isFinite(numberValue)) {
            return "N/A";
        }
        return Math.round(numberValue).toLocaleString("en-US") + " students";
    }

    const SUPPORT_METRIC_LABELS = [
        ["Multilingual learners", "el_pct"],
        ["Meal-program eligible", "frpm_pct"],
        ["Socioeconomically disadvantaged", "sed_pct"],
        ["Students with disabilities", "swd_pct"],
    ];

    /**
     * Build a concise early-grades summary from derived TK / kindergarten flags.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} Joined label or `N/A`.
     */
    function buildEarlyGradesSummary(properties) {
        const grades = [];
        if (properties.offers_tk_flag) {
            grades.push("Transitional Kindergarten (TK)");
        }
        if (properties.offers_kindergarten_flag) {
            grades.push("Kindergarten");
        }

        return grades.length ? grades.join(" | ") : "N/A";
    }

    /**
     * Build a friendlier campus-age summary from the derived recent-open flag.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} Summary label or `N/A`.
     */
    function buildCampusAgeSummary(properties) {
        const openDate = getTrimmedString(properties.open_date);
        if (!openDate) {
            return "N/A";
        }

        if (properties.recently_opened_flag) {
            return `Opened since 2018 (${escapeHtml(openDate)})`;
        }

        return `Opened ${escapeHtml(openDate)}`;
    }

    /**
     * Build chip-style campus descriptors from the grade span and grade bands.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} HTML chip list or `N/A`.
     */
    function buildCampusTypeMarkup(properties) {
        const labels = [];
        const gradeSpan = getTrimmedString(properties.grade_span_display);
        if (gradeSpan) {
            labels.push(gradeSpan);
        }

        const gradeBands = Array.isArray(properties.grade_bands)
            ? properties.grade_bands
            : [];
        gradeBands.forEach(function(value) {
            const trimmed = getTrimmedString(value);
            if (trimmed) {
                labels.push(`${trimmed} School`);
            }
        });

        const uniqueLabels = Array.from(new Set(labels));
        if (!uniqueLabels.length) {
            return "N/A";
        }

        return `
            <div class="additional-layer-popup__chip-list">
                ${uniqueLabels.map(function(label) {
                    return `<span class="additional-layer-popup__chip">${escapeHtml(label)}</span>`;
                }).join("")}
            </div>
        `;
    }

    /**
     * Build a friendlier support-profile summary from the student-support metrics.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} Profile label or `N/A`.
     */
    function buildSupportProfile(properties) {
        const thresholds = [
            Number(properties.frpm_pct) >= 60,
            Number(properties.sed_pct) >= 60,
            Number(properties.el_pct) >= 20,
            Number(properties.swd_pct) >= 15,
        ];
        const highNeedSignals = thresholds.filter(Boolean).length;

        if (highNeedSignals >= 2) {
            return "Higher-needs student population";
        }
        if (highNeedSignals === 1) {
            return "Targeted support concentration";
        }

        const hasAnyMetric = [
            properties.frpm_pct,
            properties.sed_pct,
            properties.el_pct,
            properties.swd_pct,
        ].some(function(value) {
            return Number.isFinite(Number(value));
        });
        return hasAnyMetric ? "General student support profile" : "N/A";
    }

    /**
     * Build translated support metrics for popup display.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} HTML markup or `N/A`.
     */
    function buildSupportMetricMarkup(properties) {
        const items = SUPPORT_METRIC_LABELS
            .map(function(metric) {
                const label = metric[0];
                const key = metric[1];
                const value = formatPct(properties[key]);
                if (value === "N/A") {
                    return "";
                }

                return `
                    <div class="additional-layer-popup__metric-item">
                        <span class="additional-layer-popup__metric-label">${escapeHtml(label)}</span>
                        <span class="additional-layer-popup__metric-value">${escapeHtml(value)}</span>
                    </div>
                `;
            })
            .filter(Boolean);

        if (!items.length) {
            return "N/A";
        }

        return `<div class="additional-layer-popup__metric-list">${items.join("")}</div>`;
    }

    /**
     * Build a chip for the high-level support summary.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} HTML chip markup or `N/A`.
     */
    function buildSupportProfileMarkup(properties) {
        const profile = buildSupportProfile(properties);
        if (profile === "N/A") {
            return "N/A";
        }

        return `
            <div class="additional-layer-popup__chip-list">
                <span class="additional-layer-popup__chip additional-layer-popup__chip--support">
                    ${escapeHtml(profile)}
                </span>
            </div>
        `;
    }

    /**
     * Build the preview banner shown above the popup rows.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} HTML banner markup, or an empty string when unavailable.
     */
    function buildSchoolPreviewBanner(properties) {
        const previewUrl = getTrimmedString(properties.school_preview_url);
        if (!previewUrl) {
            return "";
        }

        const schoolName = getTrimmedString(properties.school_name) || "School";
        const websiteUrl = getTrimmedString(properties.website_url);
        const imageMarkup = `
            <img
                class="additional-layer-popup__media-image"
                src="${escapeHtml(previewUrl)}"
                alt="${escapeHtml(schoolName)} aerial preview"
                loading="lazy"
                referrerpolicy="no-referrer"
            >
        `;

        return `
            <div class="additional-layer-popup__media">
                ${websiteUrl
                    ? `<a href="${escapeHtml(websiteUrl)}" target="_blank" rel="noopener noreferrer">${imageMarkup}</a>`
                    : imageMarkup}
                <div class="additional-layer-popup__media-caption">Aerial preview centered on campus coordinates.</div>
            </div>
        `;
    }

    /**
     * Build the ordered rows rendered inside a school popup.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {{ label: string, value: string }[]} Popup rows for the feature.
     */
    function buildSchoolRows(properties) {
        const hasGrades = Boolean(getTrimmedString(properties.grade_span_display));
        const rows = [
            {
                label: "District",
                value: formatTextValue(properties.district_name),
            },
            {
                label: "Address",
                value: formatTextValue(properties.full_address),
            },
            {
                label: "Grades",
                value: buildCampusTypeMarkup(properties),
            },
            {
                label: "Early Grades",
                value: buildEarlyGradesSummary(properties),
            },
            {
                label: "Enrollment",
                value: formatEnrollment(properties.enrollment_total),
            },
            {
                label: "Funding Type",
                value: formatTextValue(properties.funding_type),
            },
            {
                label: "Charter",
                value: formatTextValue(properties.charter_label),
            },
            {
                label: "Magnet",
                value: formatTextValue(properties.magnet_label),
            },
            {
                label: "Title I",
                value: formatTextValue(properties.title_i_label),
            },
            {
                label: "Campus Age",
                value: buildCampusAgeSummary(properties),
            },
            {
                label: "Locale",
                value: formatTextValue(properties.locale),
            },
            {
                label: "Student Support Snapshot",
                value: buildSupportProfileMarkup(properties),
            },
            {
                label: "Student Support Mix",
                value: buildSupportMetricMarkup(properties),
            },
            {
                label: "Website",
                value: buildExternalLink(properties.website_url, "Visit school website"),
            },
        ];

        const classificationRows = [
            {
                label: hasGrades ? "Type (dataset)" : "School Type",
                value: hasGrades
                    ? `<span class="additional-layer-popup__secondary-value">${formatTextValue(properties.school_type)}</span>`
                    : formatTextValue(properties.school_type),
            },
            {
                label: hasGrades ? "Level (dataset)" : "School Level",
                value: hasGrades
                    ? `<span class="additional-layer-popup__secondary-value">${formatTextValue(properties.school_level)}</span>`
                    : formatTextValue(properties.school_level),
            },
        ];

        if (hasGrades) {
            rows.push.apply(rows, classificationRows);
            return rows;
        }

        return rows.slice(0, 2).concat(classificationRows, rows.slice(2));
    }

    /**
     * Build the full school popup markup.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildSchoolPopupContent(properties) {
        return renderPopupCard({
            title: getTrimmedString(properties.school_name) || "School",
            rows: buildSchoolRows(properties),
            banner: buildSchoolPreviewBanner(properties),
            sizeVariant: "wide",
            heightVariant: "tall",
        });
    }

    registerPopupBuilder("buildSchoolPopupContent", buildSchoolPopupContent);
})();
