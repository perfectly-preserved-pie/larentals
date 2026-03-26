(function() {
    "use strict";

    const popupApi = window.additionalLayerPopups;
    const popupUtils = popupApi && popupApi.utils;
    const popupRuntime = popupApi && popupApi.runtime;
    const registerPopupBuilder = popupRuntime && popupRuntime.registerPopupBuilder;

    if (!popupUtils || typeof registerPopupBuilder !== "function") {
        console.error("Additional layer popup utils did not load before the crime popup builder.");
        return;
    }

    const formatPopupDate = popupUtils.formatPopupDate;
    const formatTextValue = popupUtils.formatTextValue;
    const militaryToStandard = popupUtils.militaryToStandard;
    const renderPopupCard = popupUtils.renderPopupCard;

    /**
     * Build the detail rows rendered in a crime popup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the crime record.
     * @returns {{ label: string, value: string }[]} Popup rows for the feature.
     */
    function buildCrimeRows(properties) {
        return [
            {
                label: "DR No",
                value: formatTextValue(properties.dr_no),
            },
            {
                label: "Date Occurred",
                value: formatPopupDate(properties.date_occ),
            },
            {
                label: "Time Occurred",
                value: militaryToStandard(properties.time_occ),
            },
            {
                label: "Crime Code Description",
                value: formatTextValue(properties.crm_cd_desc),
            },
            {
                label: "Victim Age",
                value: formatTextValue(properties.vict_age),
            },
            {
                label: "Victim Sex",
                value: formatTextValue(properties.vict_sex),
            },
            {
                label: "Premise Description",
                value: formatTextValue(properties.premis_desc),
            },
            {
                label: "Weapon Description",
                value: formatTextValue(properties.weapon_desc),
            },
            {
                label: "Status Description",
                value: formatTextValue(properties.status_desc),
            },
        ];
    }

    /**
     * Build the complete crime popup markup.
     *
     * @param {Record<string, unknown>} properties Feature properties for the crime record.
     * @returns {string} HTML string bound to the Leaflet popup.
     */
    function buildCrimePopupContent(properties) {
        return renderPopupCard({
            title: "Crime Info",
            rows: buildCrimeRows(properties),
        });
    }

    registerPopupBuilder("buildCrimePopupContent", buildCrimePopupContent);
})();
