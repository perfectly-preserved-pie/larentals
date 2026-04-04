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
        return [
            {
                label: "District",
                value: formatTextValue(properties.district_name),
            },
            {
                label: "Address",
                value: formatTextValue(properties.full_address),
            },
            {
                label: "School Type",
                value: formatTextValue(properties.school_type),
            },
            {
                label: "School Level",
                value: formatTextValue(properties.school_level),
            },
            {
                label: "Grades",
                value: formatTextValue(properties.grade_span_display),
            },
            {
                label: "Enrollment",
                value: formatEnrollment(properties.enrollment_total),
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
                label: "Virtual",
                value: formatTextValue(properties.virtual_label),
            },
            {
                label: "Title I",
                value: formatTextValue(properties.title_i_label),
            },
            {
                label: "Locale",
                value: formatTextValue(properties.locale),
            },
            {
                label: "Student Support",
                value: buildSchoolSupportSummary(properties),
            },
            {
                label: "Website",
                value: buildExternalLink(properties.website_url, "Visit school website"),
            },
        ];
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
