"""Browser resource restrictions shared by every Flask response."""

from collections.abc import Callable, Sequence

from flask import Flask, Response


# Mantine's pre_render_color_scheme index hook is outside app.csp_hashes().
# This authorizes its exact installed script; upgrades that change the hook
# must update the hash and pass the browser CSP checks again.
MANTINE_COLOR_SCHEME_HASH = "'sha256-Akvaf02pjGZ/mltYVmCyGYi5F2Ty6cL3/jb9jVewsYM='"
# Gesture recognition compiles MediaPipe WebAssembly. wasm-unsafe-eval permits
# that compilation without allowing JavaScript eval() or Function(). React and
# Leaflet still need inline styles for component layout and map positioning.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "script-src 'self' 'wasm-unsafe-eval' {script_hashes} https://cdn.jsdelivr.net/npm/@turf/turf@7.3.0/turf.min.js https://cdn.jsdelivr.net/npm/sweetalert2@11.26.24/dist/sweetalert2.all.min.js https://cdn.jsdelivr.net/npm/leaflet.heat@0.2.0/dist/leaflet-heat.js https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js https://cdn.jsdelivr.net/npm/@map-gesture-controls/leaflet@1.0.0/ https://cdn.jsdelivr.net/npm/@map-gesture-controls/core@1.0.0/+esm https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/+esm https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/ https://plausible.automateordie.dev/js/pa-DWgFshrhRptVOrZUWP7Ia.js",
    "script-src-attr 'none'",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net/npm/bootstrap@5.3.6/dist/css/bootstrap.min.css https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css https://cdn.jsdelivr.net/npm/@map-gesture-controls/leaflet@1.0.0/dist/style.css https://use.fontawesome.com/releases/v6.7.2/css/all.css https://api.mapbox.com/mapbox-gl-js/v3.23.1/mapbox-gl.css",
    "font-src 'self' https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/ https://use.fontawesome.com/releases/v6.7.2/webfonts/",
    "img-src 'self' data: https://ik.imagekit.io https://tile.openstreetmap.org https://api.mapbox.com https://cache.gis.lacounty.gov https://services.arcgisonline.com https://api.iconify.design",
    "connect-src 'self' https://plausible.automateordie.dev/api/event https://api.iconify.design https://api.simplesvg.com https://api.unisvg.com https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/ https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "frame-src https://maps.google.com https://www.google.com",
    "worker-src 'none'",
    "form-action 'self'",
])


def register_security_headers(
    server: Flask, script_hashes: Callable[[], Sequence[str]] = tuple,
) -> None:
    """Apply the browser policy at the app boundary, including error responses.

    Keeping this in Flask makes the policy independent of Pangolin configuration.
    Resolve Dash's script hashes after request handling because Pages registers
    additional inline callbacks during its first-request setup. Hashes come from
    registered code, never response HTML that might contain untrusted markup.
    Inline styles remain necessary for React and Leaflet positioning.
    """

    @server.after_request
    def add_content_security_policy(response: Response) -> Response:
        """Attach one enforced policy before Flask sends a response.

        Assignment replaces an existing app header so repeated policy values
        cannot accidentally impose conflicting restrictions on the same response.
        """
        hashes = " ".join(dict.fromkeys([*script_hashes(), MANTINE_COLOR_SCHEME_HASH]))
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY.format(script_hashes=hashes)
        return response
