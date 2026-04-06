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

    /**
     * Build the student-support summary row.
     *
     * @param {Record<string, unknown>} properties School feature properties.
     * @returns {string} Joined support metrics or `N/A`.
     */
    function buildSchoolSupportSummary(properties) {
        const fragments = [];
        const metrics = [
            ["EL", properties.el_pct],
            ["FRPM", properties.frpm_pct],
            ["SED", properties.sed_pct],
            ["SWD", properties.swd_pct],
        ];

        metrics.forEach(function(metric) {
            const label = metric[0];
            const value = formatPct(metric[1]);
            if (value !== "N/A") {
                fragments.push(`${escapeHtml(label)} ${escapeHtml(value)}`);
            }
        });

        return fragments.length ? fragments.join(" | ") : "N/A";
    }

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
                value: formatTextValue(properties.grade_span_display),
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
                label: "Support Profile",
                value: buildSupportProfile(properties),
            },
            {
                label: "Support Metrics",
                value: buildSchoolSupportSummary(properties),
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
