// This is a JavaScript file to customize the Leaflet popup
// It should be used with dl.GeoJSON's `onEachFeature` option
// See https://github.com/perfectly-preserved-pie/larentals/issues/86#issuecomment-1585304809

/**
 * @typedef {{ properties?: Record<string, unknown> }} PopupFeature
 */

/**
 * @typedef {{
 *   bindPopup: (content: string, options?: Record<string, unknown>) => unknown,
 *   on: (eventName: string, handler: () => void) => unknown,
 *   getPopup?: () => ({ getElement?: () => HTMLElement | null } | null),
 *   _map?: { getContainer?: () => HTMLElement | null } | null,
 * }} PopupLayer
 */

window.dash_props = Object.assign({}, window.dash_props, {
    module: {
        /**
         * Build and bind the main property popup for a GeoJSON listing feature.
         *
         * @param {PopupFeature} feature GeoJSON feature emitted by Dash Leaflet.
         * @param {PopupLayer} layer Leaflet layer receiving the popup binding.
         * @returns {void} Does not return a value; mutates the supplied layer.
         */
        on_each_feature: function(feature, layer) {
            //console.log("Feature properties:", feature.properties);
            if (!feature.properties) {
                console.warn("Feature properties are missing.");
                return;
            }

            const data = feature.properties; // Use feature.properties directly
            const encodedData = encodeURIComponent(JSON.stringify(data)); // Encode the data as a JSON for the reportListing function

            /**
             * Converts placeholder values (e.g., "None", "null", empty strings) to null,
             * returning the trimmed string for any other input.
             *
             * @param {unknown} value Raw value supplied from the GeoJSON properties.
             * @returns {string|null} Normalized string or null when the value is missing/placeholder.
             */
            const normalizeNullableString = (value) => {
                if (value === null || value === undefined) {
                    return null;
                }
                const normalized = String(value).trim();
                if (!normalized || ["none", "null", "nan"].includes(normalized.toLowerCase())) {
                    return null;
                }
                return normalized;
            };

            /**
             * Strip a terminal `.0` without disturbing meaningful decimals like `475.08`.
             *
             * @param {string|number|null|undefined} value String or numeric display value.
             * @returns {string|number|null|undefined} Cleaned display value preserving the input shape when possible.
             */
            const stripTrailingPointZero = (value) => {
                if (value === null || value === undefined) return value;
                const cleaned = String(value).replace(/\.0$/, "");
                if (typeof value === "number") {
                    const asNum = Number(cleaned);
                    return Number.isNaN(asNum) ? value : asNum;
                }
                return cleaned;
            };

            /**
             * Format lot size with thousands separators while preserving up to two decimals.
             *
             * @param {unknown} value Raw lot-size value from the listing payload.
             * @returns {string|null} Human-readable lot size, or `null` when the value is unusable.
             */
            const formatLotSize = (value) => {
                if (value === null || value === undefined) return null;
                if (typeof value === "string") {
                    const normalized = value.replace(/,/g, "").trim();
                    if (!normalized || ["none", "null", "nan"].includes(normalized.toLowerCase())) return null;
                    const num = Number(normalized);
                    if (Number.isNaN(num)) return null;
                    const formatted = num % 1 === 0
                        ? num.toLocaleString("en-US")
                        : num.toLocaleString("en-US", { maximumFractionDigits: 2 });
                    return stripTrailingPointZero(formatted);
                }

                const num = Number(value);
                if (Number.isNaN(num)) return null;
                const formatted = num % 1 === 0
                    ? num.toLocaleString("en-US")
                    : num.toLocaleString("en-US", { maximumFractionDigits: 2 });
                return stripTrailingPointZero(formatted);
            };

            /**
             * Format a numeric value as US currency without decimals.
             *
             * @param {unknown} value Raw currency-like value from the listing data.
             * @returns {string} Currency string, or `"Unknown"` when the value is missing or invalid.
             */
            function formatCurrency(value) {
                if (value === null || value === undefined || value === "") return "Unknown";

                const n = Number(value);
                if (!Number.isFinite(n)) return "Unknown";

                return `$${n.toLocaleString()}`;
            }

            const listingUrl = normalizeNullableString(data.listing_url);
            const mlsPhoto = normalizeNullableString(data.mls_photo);

            /**
             * Convert a street address string into title case for popup display.
             *
             * @param {string} str Address string to normalize.
             * @returns {string} Title-cased address string.
             */
            function toTitleCase(str) {
                return str.replace(/\w\S*/g, function(txt) {
                    return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
                });
            }

            const fullStreetAddressRaw = stripTrailingPointZero(normalizeNullableString(data.full_street_address)) || "Unknown Address";
            const fullStreetAddress = toTitleCase(fullStreetAddressRaw);
            const lotSizeDisplay = formatLotSize(data.lot_size);
            const mlsNumberDisplay = stripTrailingPointZero(data.mls_number);

            // Determine property subtype flags
            const subtype = (data?.subtype ?? "Unknown").toString();   // Coerce to string for includes()
            const isSfr = subtype.includes("SFR") || subtype.includes("Single Family Residence");

            /**
             * Render the popup title block, linking the address when a listing URL exists.
             *
             * @param {string|number} address Display-ready street address.
             * @param {string|null} listingUrlValue Listing detail URL, if available.
             * @returns {string} HTML string for the popup heading.
             */
            function getListingUrlBlock(address, listingUrlValue) {
                if (!listingUrlValue) {
                    return `
                        <div style="text-align: center;">
                            <h5>${address}</h5>
                        </div>
                    `;
                }
                return `
                    <div style="text-align: center;">
                        <h5><a href='${listingUrlValue}' referrerPolicy='noreferrer' target='_blank'>${address}</a></h5>
                    </div>
                `;
            }

            /**
             * Render the property photo row, optionally wrapping the image in the listing URL.
             *
             * @param {string|null} photoUrl Image URL for the listing.
             * @param {string|null} listingUrlValue Listing detail URL, if available.
             * @returns {string} HTML string for the image row, or an empty string.
             */
            function buildImageRow(photoUrl, listingUrlValue) {
                if (!photoUrl) {
                    return '';
                }
                const imageTag = `<img src="${photoUrl}" alt="Property Image" style="width:100%;height:auto;">`;
                if (listingUrlValue) {
                    return `
                        <div style="position: relative;">
                            <a href="${listingUrlValue}" target="_blank" referrerPolicy="noreferrer">
                                ${imageTag}
                            </a>
                        </div>
                    `;
                }
                return `
                    <div style="position: relative;">
                        ${imageTag}
                    </div>
                `;
            }

            /**
             * Render the Palisades fire warning banner when the listing is flagged.
             *
             * @param {Record<string, unknown>} popupData Listing properties used by the popup.
             * @returns {string} Warning-banner HTML, or an empty string when not applicable.
             */
            function getPalisadesFireAlertBlock(popupData) {
                if (popupData.affected_by_palisades_fire === true || popupData.affected_by_palisades_fire === "True") {
                    return `
                        <div style="color: red; text-align: center;">
                            ⚠️ Affected by Palisades Fire. Please verify at <a href="https://recovery.lacounty.gov/palisades-fire/" target="_blank" style="color: red;">recovery.lacounty.gov</a>.
                        </div>
                    `;
                }
                return '';
            }

            /**
             * Render the Eaton fire warning banner when the listing is flagged.
             *
             * @param {Record<string, unknown>} popupData Listing properties used by the popup.
             * @returns {string} Warning-banner HTML, or an empty string when not applicable.
             */
            function getEatonFireAlertBlock(popupData) {
                if (popupData.affected_by_eaton_fire === true || popupData.affected_by_eaton_fire === "True") {
                    return `
                        <div style="color: red; text-align: center;">
                            ⚠️ Affected by Eaton Fire. Please verify at <a href="https://recovery.lacounty.gov/eaton-fire/" target="_blank" style="color: red;">recovery.lacounty.gov</a>.
                        </div>
                    `;
                }
                return '';
            }

            /**
             * Format a date-like value as `YYYY-MM-DD`.
             *
             * @param {unknown} dateString Date value pulled from the listing payload.
             * @returns {string} ISO-style date string, or `"Unknown"` when missing.
             */
            function formatDate(dateString) {
                if (!dateString) return "Unknown";
                const date = new Date(dateString);
                return date.toISOString().split('T')[0];
            }

            // Conditionally format the listing URL as a hyperlink or plain text
            const listingUrlBlock = getListingUrlBlock(fullStreetAddress, listingUrl);

            // Conditionally include the property image row if the image URL is available
            const imageRow = buildImageRow(mlsPhoto, listingUrl);

            // Conditionally format the phone number as a tel: link or plain text
            const phoneNumberBlock = data.phone_number ? `
                <a href="tel:${data.phone_number}">${data.phone_number}</a>
            ` : 'Unknown';

            /**
             * Build the lease-page popup body for a single listing.
             *
             * @param {Record<string, unknown>} popupData Listing properties shown in the popup.
             * @returns {string} HTML string bound to the Leaflet popup.
             */
            function generateLeasePopupContent(popupData) {
                return `
                    <div>
                        ${getPalisadesFireAlertBlock(popupData)}
                        ${getEatonFireAlertBlock(popupData)}
                        ${imageRow}
                        ${listingUrlBlock}
                        <div class="property-card" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                            <!-- Listed Date -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listed Date</span>
                                <span class="value">${formatDate(popupData.listed_date)}</span>
                            </div>
                            <!-- Listing ID (MLS#) -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listing ID (MLS#)</span>
                                <span class="value">${mlsNumberDisplay}</span>
                            </div>
                            <!-- List Office Phone -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">List Office Phone</span>
                                <span class="value">${phoneNumberBlock}</span>
                            </div>
                            <!-- Rental Price -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Rental Price</span>
                                <span class="value">${formatCurrency(popupData.list_price)}</span>
                            </div>
                            <!-- Security Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Security Deposit</span>
                                <span class="value">${formatCurrency(popupData.security_deposit)}</span>
                            </div>
                            <!-- Pet Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Pet Deposit</span>
                                <span class="value">${formatCurrency(popupData.pet_deposit)}</span>
                            </div>
                            <!-- Key Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Key Deposit</span>
                                <span class="value">${formatCurrency(popupData.key_deposit)}</span>
                            </div>
                            <!-- Other Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Other Deposit</span>
                                <span class="value">${formatCurrency(popupData.other_deposit)}</span>
                            </div>
                            <!-- Square Feet -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Square Feet</span>
                                <span class="value">${popupData.sqft ? `${popupData.sqft.toLocaleString()} sq. ft` : "Unknown"}</span>
                            </div>
                            <!-- Price Per Square Foot -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Price Per Square Foot</span>
                                <span class="value">${popupData.ppsqft ? `$${popupData.ppsqft.toLocaleString()}` : "Unknown"}</span>
                            </div>
                            <!-- Bedrooms/Bathrooms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Bedrooms/Bathrooms</span>
                                <span class="value">${popupData.bedrooms}/${popupData.total_bathrooms}</span>
                            </div>
                            <!-- Parking Spaces -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Parking Spaces</span>
                                <span class="value">${popupData.parking_spaces || "Unknown"}</span>
                            </div>
                            <!-- Pets Allowed? -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Pets Allowed?</span>
                                <span class="value">${popupData.pet_policy || "Unknown"}</span>
                            </div>
                            <!-- Furnished? -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Furnished?</span>
                                <span class="value">${popupData.furnished || "Unknown"}</span>
                            </div>
                            <!-- Laundry Features -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Laundry Features</span>
                                <span class="value" style="white-space: normal; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word;">
                                    ${popupData.laundry || "Unknown"}
                                </span>
                            </div>
                            <!-- Year Built -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Year Built</span>
                                <span class="value">${popupData.year_built || "Unknown"}</span>
                            </div>
                            <!-- Rental Terms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Rental Terms</span>
                                <span class="value">${popupData.terms || "Unknown"}</span>
                            </div>
                            <!-- Physical Sub Type -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Physical Sub Type</span>
                                <span class="value">${subtype || "Unknown"}</span>
                            </div>
                            <!-- ISP Options -->
                            <div class="property-row" style="display:flex; justify-content:space-between; align-items:flex-start; padding:8px; border-bottom:1px solid #ddd; gap:12px;">
                                <span class="label" style="font-weight:bold;">ISP Options</span>
                                <div class="value" style="text-align:right;">
                                ${window.larentals?.isp?.renderIspOptionsPlaceholderHtml(popupData.mls_number) ?? ""}
                                </div>
                            </div>
                        </div>
                        <div style="text-align: center; margin-top: 10px;">
                            <a href="#" title="Report Listing" onclick='reportListing(decodeURIComponent("${encodedData}"))' style="text-decoration: none; color: red;">
                                <i class="fa-solid fa-flag" style="font-size:1.25em; vertical-align: middle;"></i>
                                <span style="vertical-align: middle; margin-left: 5px;">Report Listing</span>
                            </a>
                        </div>
                    </div>
                `;
            }

            /**
             * Build the buy-page popup body for a single listing.
             *
             * @param {Record<string, unknown>} popupData Listing properties shown in the popup.
             * @returns {string} HTML string bound to the Leaflet popup.
             */
            function generateBuyPopupContent(popupData) {
                // Include parking spaces if subtype is not 'SFR' or 'Single Family Residence'
                let parkingContent = '';
                if (!isSfr) {
                    parkingContent = `
                        <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                            <span class="label" style="font-weight: bold;">Parking Spaces</span>
                            <span class="value">${popupData.garage_spaces || "Unknown"}</span>
                        </div>
                    `;
                }

                return `
                    <div>
                        ${getPalisadesFireAlertBlock(popupData)}
                        ${getEatonFireAlertBlock(popupData)}
                        ${imageRow}
                        ${listingUrlBlock}
                        <div class="property-card" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                            <!-- Listed Date -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listed Date</span>
                                <span class="value">${formatDate(popupData.listed_date)}</span>
                            </div>
                            <!-- Listing ID (MLS#) -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listing ID (MLS#)</span>
                                <span class="value">${mlsNumberDisplay}</span>
                            </div>
                            <!-- List Office Phone -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">List Office Phone</span>
                                <span class="value">${phoneNumberBlock || "Unknown"}</span>
                            </div>
                            <!-- List Price -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">List Price</span>
                                <span class="value">${formatCurrency(popupData.list_price)}</span>
                            </div>
                            <!-- HOA Fee -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">HOA Fee</span>
                                <span class="value">${formatCurrency(popupData.hoa_fee)}</span>
                            </div>
                            <!-- HOA Fee Frequency -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">HOA Fee Frequency</span>
                                <span class="value">${popupData.hoa_fee_frequency || "Unknown"}</span>
                            </div>
                            <!-- Square Feet -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Square Feet</span>
                                <span class="value">${popupData.sqft ? `${popupData.sqft.toLocaleString()} sq. ft` : "Unknown"}</span>
                            </div>
                            <!-- Price Per Square Foot -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Price Per Square Foot</span>
                                <span class="value">${formatCurrency(popupData.ppsqft)}</span>
                            </div>
                            <!-- Lot Size -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Lot Size</span>
                                <span class="value">${lotSizeDisplay ? `${lotSizeDisplay} sq. ft` : "Unknown"}</span>
                            </div>
                            <!-- Bedrooms/Bathrooms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Bedrooms/Bathrooms</span>
                                <span class="value">${popupData.bedrooms}/${popupData.total_bathrooms}</span>
                            </div>
                            ${parkingContent}
                            <!-- Year Built -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Year Built</span>
                                <span class="value">${popupData.year_built || "Unknown"}</span>
                            </div>
                            <!-- Physical Sub Type -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Physical Sub Type</span>
                                <span class="value">${subtype}</span>
                            </div>
                            <!-- ISP Options -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: flex-start; padding: 8px; border-bottom: 1px solid #ddd; gap: 12px;">
                                <span class="label" style="font-weight: bold;">ISP Options</span>
                                <div class="value" style="text-align: right;">
                                    ${window.larentals?.isp?.renderIspOptionsPlaceholderHtml(popupData.mls_number) ?? ""}
                                </div>
                            </div>
                        </div>
                        <div style="text-align: center; margin-top: 10px;">
                            <a href="#" title="Report Listing" onclick='reportListing(decodeURIComponent("${encodedData}"))' style="text-decoration: none; color: red;">
                                <i class="fa-solid fa-flag" style="font-size:1.25em; vertical-align: middle;"></i>
                                <span style="vertical-align: middle; margin-left: 5px;">Report Listing</span>
                            </a>
                        </div>
                    </div>
                `;
            }

            /**
             * Load ISP options into the popup once Leaflet has inserted the popup DOM.
             *
             * @returns {void} Does not return a value; mutates the popup container in place.
             */
            function handlePopupOpen() {
                const el = layer.getPopup?.()?.getElement?.();
                if (!el) return;

                const ispApi = window.larentals?.isp;
                if (!ispApi) return;

                ispApi.hydrateIspOptionsInPopup(el);
            }

            // Determine which popup content to generate based on context
            // Infer page type from context or URL path
            const path = String(window.location?.pathname || "").toLowerCase();
            const isBuyPage = path === "/buy" || path.startsWith("/buy");

            let popupContent = "";
            if (isBuyPage) {
                popupContent = generateBuyPopupContent(data);
            } else {
                popupContent = generateLeasePopupContent(data);
            }

            // Use Leaflet's map size to determine the popup size
            const isMobile = L.Browser.mobile || window.innerWidth < 768; 
            // Clamp popup size to the visible map container so it never exceeds the viewport.
            // Still keep the "lease-style" caps (desktop: 350x650, mobile: 225x405).
            const mapEl = layer?._map?.getContainer?.() ?? null;
            const rect = mapEl?.getBoundingClientRect?.() ?? null;

            const availW = Math.floor(Math.min(window.innerWidth, rect?.width ?? window.innerWidth));
            const availH = Math.floor(Math.min(window.innerHeight, rect?.height ?? window.innerHeight));

            const padding = isMobile ? 24 : 48; // breathing room around popup
            const leaseLikeMaxWidthCap = isMobile ? 225 : 350;
            const leaseLikeMaxHeightCap = isMobile ? 405 : 650;

            const maxWidth = Math.max(
                200,
                Math.min(leaseLikeMaxWidthCap, availW - padding)
            );

            const maxHeight = Math.max(
                220,
                Math.min(leaseLikeMaxHeightCap, availH - padding)
            );

            // Bind the popup to the layer with the generated content and size constraints
            layer.bindPopup(
                popupContent,
                {
                    maxWidth: maxWidth,
                    maxHeight: maxHeight,
                    keepInView: false,
                    autoPanPadding: [10, 10],
                    closeButton: true,
                    //closeOnClick: false,
                    className: 'responsive-popup',
                }
            );
            // Hydrate ISP options when the popup opens
            layer.on("popupopen", handlePopupOpen);
        }
    }
});
