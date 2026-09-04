"""Price-labelled map markers.

Every listing pin carries its price, coloured on a cheap-to-expensive ramp, so
cost is scannable straight off the map instead of one popup at a time.

The ramp is anchored to the 10th and 90th percentile of each page's real prices
rather than to min and max, because a handful of outliers would otherwise flatten
everything else into one colour. Measured over the current data:

    lease  p10 $1,950     p90 $4,000
    buy    p10 $449,000   p90 $949,000

Green through red is what was asked for. It is also the one ramp that
red-green colourblind viewers cannot read, so the endpoints live in
`PRICE_RAMP_START_HUE` / `PRICE_RAMP_END_HUE` and swapping them to a
blue-to-orange scale is a two-number change.
"""

from dash_extensions.javascript import assign

# HSL hues for the cheap and expensive ends of the scale.
PRICE_RAMP_START_HUE = 130  # green
PRICE_RAMP_END_HUE = 0  # red

LEASE_PRICE_LOW = 1950
LEASE_PRICE_HIGH = 4000
BUY_PRICE_LOW = 449_000
BUY_PRICE_HIGH = 949_000

build_price_marker = assign(
    """function(feature, latlng, context){
    const props = feature.properties || {};
    const price = Number(props.list_price);

    // The two pages differ by three orders of magnitude, so the scale has to
    // know which one it is on. Same test the popup detail fetch uses.
    const path = String(window.location.pathname || '').toLowerCase();
    const isBuy = path === '/buy' || path.indexOf('/buy') === 0;
    const low = isBuy ? %(buy_low)d : %(lease_low)d;
    const high = isBuy ? %(buy_high)d : %(lease_high)d;

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

    let hue = %(start_hue)d;
    if (Number.isFinite(price) && high > low) {
        const t = Math.max(0, Math.min(1, (price - low) / (high - low)));
        hue = %(start_hue)d + t * (%(end_hue)d - %(start_hue)d);
    }
    const background = Number.isFinite(price)
        ? 'hsl(' + hue.toFixed(0) + ', 62%%, 38%%)'
        : '#6b7280';

    const label = Number.isFinite(price) ? formatPrice(price) : 'n/a';
    const width = 14 + label.length * 7;

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
        + ' data-subtype="' + esc(props.subtype) + '"';

    const marker = L.marker(latlng, {
        icon: L.divIcon({
            className: 'price-marker-icon',
            html: '<span class="price-marker" style="background:' + background + '"'
                + dataAttrs + '>' + label + '</span>',
            iconSize: [width, 20],
            // Anchor at the bottom centre so the pill sits above the point it
            // describes rather than covering it.
            iconAnchor: [width / 2, 22],
            popupAnchor: [0, -22]
        })
    });
    // The results panel reads listing data straight off the layers in view, so
    // the feature has to travel with the marker.
    marker.feature = feature;
    return marker;
}"""
    % {
        "buy_low": BUY_PRICE_LOW,
        "buy_high": BUY_PRICE_HIGH,
        "lease_low": LEASE_PRICE_LOW,
        "lease_high": LEASE_PRICE_HIGH,
        "start_hue": PRICE_RAMP_START_HUE,
        "end_hue": PRICE_RAMP_END_HUE,
    }
)
