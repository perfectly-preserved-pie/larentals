"""Price-labelled map markers.

Every listing pin carries its price, coloured on a cheap-to-expensive ramp, so
cost is scannable straight off the map instead of one popup at a time.

The colour itself comes from `assets/js/price_scale.js`, which ranks a price
against the listings currently in view rather than against a fixed band. That
module owns the ramp; this one owns the marker.
"""

from dash_extensions.javascript import assign

build_price_marker = assign(
    """function(feature, latlng, context){
    // At zooms where nothing clusters, this is the only callback that sees the
    // map, so it publishes the handle too.
    window.larentals = window.larentals || {};
    if (context && context.map) window.larentals.map = context.map;

    const props = feature.properties || {};
    const price = Number(props.list_price);

    const formatPrice = function(value) {
        if (!Number.isFinite(value)) return '?';
        if (value >= 1000000) {
            const millions = value / 1000000;
            return '$' + (millions >= 10 ? Math.round(millions) : millions.toFixed(1)) + 'M';
        }
        if (value >= 1000) {
            const thousands = value / 1000;
            return '$' + (thousands >= 100 ? Math.round(thousands) : thousands.toFixed(1)) + 'k';
        }
        return '$' + Math.round(value);
    };

    // First paint. The scale recolours every pin once it knows what is in view,
    // so this only has to be right before the map has drawn anything.
    const scale = (window.larentals || {}).priceScale;
    const background = scale ? scale.colorFor(price) : '#6b7280';

    const label = Number.isFinite(price) ? formatPrice(price) : 'n/a';
    // 1.2x the old size. The pill is sized here rather than in CSS because
    // Leaflet needs the box up front to place and anchor the icon, so these
    // numbers and the ones in popup.css have to be changed together.
    const width = 17 + label.length * 8.4;

    // The results panel reads these straight off the DOM, which keeps it
    // independent of any handle on the Leaflet map object.
    const esc = function(v) {
        return String(v === null || v === undefined ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    };
    const dataAttrs = ' data-mls="' + esc(props.mls_number) + '"'
        + ' data-price="' + (Number.isFinite(price) ? price : '') + '"'
        + ' data-address="' + esc(props.full_street_address) + '"'
        + ' data-beds="' + esc(props.bedrooms) + '"'
        + ' data-baths="' + esc(props.total_bathrooms) + '"'
        + ' data-sqft="' + esc(props.sqft) + '"'
        + ' data-subtype="' + esc(props.subtype) + '"'
        + ' data-ppsqft="' + esc(props.ppsqft) + '"'
        + ' data-listed="' + esc(props.listed_date) + '"';

    const marker = L.marker(latlng, {
        icon: L.divIcon({
            className: 'price-marker-icon',
            html: '<span class="price-marker" style="background:' + background + '"'
                + dataAttrs + '>' + label + '</span>',
            iconSize: [width, 24],
            // Anchor at the bottom centre so the pill sits above the point it
            // describes rather than covering it.
            iconAnchor: [width / 2, 26],
            // Clears the pin at the size it is while a popup is open, which is
            // the grown one: a pin is always selected when its popup shows, and
            // it grows upward from its bottom edge (popup.css), so its top is
            // well above the 24px box Leaflet measures. Anchoring to the box
            // instead puts the popup's tip through the pin.
            popupAnchor: [0, -45]
        })
    });
    // The results panel reads listing data straight off the layers in view, so
    // the feature has to travel with the marker.
    marker.feature = feature;
    return marker;
}"""
)
