// This is a JavaScript file to customize the Leaflet popup
// It should be used with dl.GeoJSON's `onEachFeature` option
// See https://github.com/perfectly-preserved-pie/larentals/issues/86#issuecomment-1585304809
window.dash_props = Object.assign({}, window.dash_props, {
    module: {
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

            // Strip a terminal '.0' without disturbing real decimals like 475.08
            const stripTrailingPointZero = (value) => {
                if (value === null || value === undefined) return value;
                const cleaned = String(value).replace(/\.0$/, "");
                if (typeof value === "number") {
                    const asNum = Number(cleaned);
                    return Number.isNaN(asNum) ? value : asNum;
                }
                return cleaned;
            };

            // Format lot size with commas, preserving up to two decimals and removing redundant trailing .0
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

            // Format currency with dollar sign and commas
            // And safeguard against invalid inputs
            function formatCurrency(value) {
                if (value === null || value === undefined || value === "") return "Unknown";

                const n = Number(value);
                if (!Number.isFinite(n)) return "Unknown";

                return `$${n.toLocaleString()}`;
                }

            const listingUrl = normalizeNullableString(data.listing_url);
            const mlsPhoto = normalizeNullableString(data.mls_photo);
            const fullStreetAddress = stripTrailingPointZero(normalizeNullableString(data.full_street_address)) || "Unknown Address";
            const lotSizeDisplay = formatLotSize(data.lot_size);
            const mlsNumberDisplay = stripTrailingPointZero(data.mls_number);

            // Determine property subtype flags
            const subtype = (data?.subtype ?? "Unknown").toString();   // Coerce to string for includes()
            const isSfr = subtype.includes("SFR") || subtype.includes("Single Family Residence");

            // Function to handle MLS number hyperlink
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

            // Function to handle the Palisades fire alert
            function getPalisadesFireAlertBlock(data) {
                if (data.affected_by_palisades_fire === true || data.affected_by_palisades_fire === "True") {
                    return `
                        <div style="color: red; text-align: center;">
                            ⚠️ Affected by Palisades Fire. Please verify at <a href="https://recovery.lacounty.gov/palisades-fire/" target="_blank" style="color: red;">recovery.lacounty.gov</a>.
                        </div>
                    `;
                }
                return '';
            }

            // Function to handle the Eaton fire alert
            function getEatonFireAlertBlock(data) {
                if (data.affected_by_eaton_fire === true || data.affected_by_eaton_fire === "True") {
                    return `
                        <div style="color: red; text-align: center;">
                            ⚠️ Affected by Eaton Fire. Please verify at <a href="https://recovery.lacounty.gov/eaton-fire/" target="_blank" style="color: red;">recovery.lacounty.gov</a>.
                        </div>
                    `;
                }
                return '';
            }

            // Function to format date string
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

            // Function to generate popup content for lease page
            function generateLeasePopupContent(data) {
                return `
                    <div>
                        ${getPalisadesFireAlertBlock(data)}
                        ${getEatonFireAlertBlock(data)}
                        ${imageRow}
                        ${listingUrlBlock}
                        <div class="property-card" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                            <!-- Listed Date -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listed Date</span>
                                <span class="value">${formatDate(data.listed_date)}</span>
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
                                <span class="value">${formatCurrency(data.list_price)}</span>
                            </div>
                            <!-- Security Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Security Deposit</span>
                                <span class="value">${formatCurrency(data.security_deposit)}</span>
                            </div>
                            <!-- Pet Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Pet Deposit</span>
                                <span class="value">${formatCurrency(data.pet_deposit)}</span>
                            </div>
                            <!-- Key Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Key Deposit</span>
                                <span class="value">${formatCurrency(data.key_deposit)}</span>
                            </div>
                            <!-- Other Deposit -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Other Deposit</span>
                                <span class="value">${formatCurrency(data.other_deposit)}</span>
                            </div>
                            <!-- Square Feet -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Square Feet</span>
                                <span class="value">${data.sqft ? `${data.sqft.toLocaleString()} sq. ft` : "Unknown"}</span>
                            </div>
                            <!-- Price Per Square Foot -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Price Per Square Foot</span>
                                <span class="value">${data.ppsqft ? `$${data.ppsqft.toLocaleString()}` : "Unknown"}</span>
                            </div>
                            <!-- Bedrooms/Bathrooms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Bedrooms/Bathrooms</span>
                                <span class="value">${data.bedrooms}/${data.total_bathrooms}</span>
                            </div>
                            <!-- Parking Spaces -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Parking Spaces</span>
                                <span class="value">${data.parking_spaces || "Unknown"}</span>
                            </div>
                            <!-- Pets Allowed? -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Pets Allowed?</span>
                                <span class="value">${data.pet_policy || "Unknown"}</span>
                            </div>
                            <!-- Furnished? -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Furnished?</span>
                                <span class="value">${data.furnished || "Unknown"}</span>
                            </div>
                            <!-- Laundry Features -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Laundry Features</span>
                                <span class="value" style="white-space: normal; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word;">
                                    ${data.laundry || "Unknown"}
                                </span>
                            </div>
                            <!-- Year Built -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Year Built</span>
                                <span class="value">${data.year_built || "Unknown"}</span>
                            </div>
                            <!-- Rental Terms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Rental Terms</span>
                                <span class="value">${data.terms || "Unknown"}</span>
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
                                ${window.larentals?.isp?.renderIspOptionsPlaceholderHtml(data.mls_number) ?? ""}
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

            // Function to generate popup content for buy page
            function generateBuyPopupContent(data) {
                // Include parking spaces if subtype is not 'SFR' or 'Single Family Residence'
                let parkingContent = '';
                if (!isSfr) {
                    parkingContent = `
                        <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                            <span class="label" style="font-weight: bold;">Parking Spaces</span>
                            <span class="value">${data.garage_spaces || "Unknown"}</span>
                        </div>
                    `;
                }

                return `
                    <div>
                        ${getPalisadesFireAlertBlock(data)}
                        ${getEatonFireAlertBlock(data)}
                        ${imageRow}
                        ${listingUrlBlock}
                        <div class="property-card" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px;">
                            <!-- Listed Date -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Listed Date</span>
                                <span class="value">${formatDate(data.listed_date)}</span>
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
                                <span class="value">${formatCurrency(data.list_price)}</span>
                            </div>
                            <!-- HOA Fee -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">HOA Fee</span>
                                <span class="value">${formatCurrency(data.hoa_fee)}</span>
                            </div>
                            <!-- HOA Fee Frequency -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">HOA Fee Frequency</span>
                                <span class="value">${data.hoa_fee_frequency || "Unknown"}</span>
                            </div>
                            <!-- Square Feet -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Square Feet</span>
                                <span class="value">${data.sqft ? `${data.sqft.toLocaleString()} sq. ft` : "Unknown"}</span>
                            </div>
                            <!-- Price Per Square Foot -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Price Per Square Foot</span>
                                <span class="value">${formatCurrency(data.ppsqft)}</span>
                            </div>
                            <!-- Lot Size -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Lot Size</span>
                                <span class="value">${lotSizeDisplay ? `${lotSizeDisplay} sq. ft` : "Unknown"}</span>
                            </div>
                            <!-- Bedrooms/Bathrooms -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Bedrooms/Bathrooms</span>
                                <span class="value">${data.bedrooms}/${data.total_bathrooms}</span>
                            </div>
                            ${parkingContent}
                            <!-- Year Built -->
                            <div class="property-row" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #ddd;">
                                <span class="label" style="font-weight: bold;">Year Built</span>
                                <span class="value">${data.year_built || "Unknown"}</span>
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
                                    ${window.larentals?.isp?.renderIspOptionsPlaceholderHtml(data.mls_number) ?? ""}
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
            layer.on("popupopen", () => {
            const el = layer.getPopup()?.getElement?.();
            if (!el) return;

            const ispApi = window.larentals?.isp;
            if (!ispApi) return;

            ispApi.hydrateIspOptionsInPopup(el);
            });
        }
    }
});