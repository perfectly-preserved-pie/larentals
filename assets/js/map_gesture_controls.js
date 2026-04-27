(function () {
    const PACKAGE_VERSION = "0.2.0";
    const MODULE_URL = `https://cdn.jsdelivr.net/npm/@map-gesture-controls/leaflet@${PACKAGE_VERSION}/+esm`;
    const STYLE_URL = `https://cdn.jsdelivr.net/npm/@map-gesture-controls/leaflet@${PACKAGE_VERSION}/dist/style.css`;
    const TOGGLE_SELECTOR = "[data-map-gesture-control='toggle']";
    const PANEL_TOGGLE_SELECTOR = "[data-map-gesture-panel='toggle']";

    let leafletMap = null;
    let controller = null;
    let modulePromise = null;
    let isActive = false;
    let isStarting = false;
    let statusTimer = null;
    const mobileViewportQuery = window.matchMedia("(max-width: 767.98px)");

    function ensurePluginStylesheet() {
        if (document.querySelector("link[data-map-gesture-controls-style='true']")) {
            return;
        }

        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = STYLE_URL;
        link.setAttribute("data-map-gesture-controls-style", "true");
        document.head.appendChild(link);
    }

    function loadGestureModule() {
        ensurePluginStylesheet();

        if (!modulePromise) {
            modulePromise = import(MODULE_URL).catch((error) => {
                modulePromise = null;
                throw error;
            });
        }

        return modulePromise;
    }

    function isUsableMap(candidate) {
        return Boolean(
            candidate &&
            typeof candidate.getContainer === "function" &&
            typeof candidate.getCenter === "function" &&
            typeof candidate.getZoom === "function" &&
            typeof candidate.panBy === "function"
        );
    }

    function hasWebGLSupport() {
        try {
            const canvas = document.createElement("canvas");
            const contextOptions = {
                alpha: false,
                antialias: false,
                depth: false,
                failIfMajorPerformanceCaveat: false,
                powerPreference: "default",
                stencil: false,
            };
            const context = canvas.getContext("webgl2", contextOptions) || canvas.getContext("webgl", contextOptions);

            if (!context) {
                return false;
            }

            const loseContext = context.getExtension("WEBGL_lose_context");
            if (loseContext && typeof loseContext.loseContext === "function") {
                loseContext.loseContext();
            }

            return true;
        } catch (error) {
            return false;
        }
    }

    function browserCanRunGestures() {
        if (!window.isSecureContext && !["localhost", "127.0.0.1"].includes(location.hostname)) {
            return "Camera access requires HTTPS.";
        }
        if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
            return "Camera access is unavailable in this browser.";
        }
        if (!hasWebGLSupport()) {
            return "Gesture control requires browser WebGL.";
        }

        return "";
    }

    function currentMap() {
        if (!isUsableMap(leafletMap)) {
            return null;
        }

        const container = leafletMap.getContainer();
        return container && container.isConnected ? leafletMap : null;
    }

    function isMobileViewport() {
        return Boolean(mobileViewportQuery.matches);
    }

    function dockGestureControl(targetMap) {
        if (!isUsableMap(targetMap)) {
            return;
        }

        const container = targetMap.getContainer();
        const controlCorner = container && container.querySelector(".leaflet-top.leaflet-left");
        const gestureControl = document.querySelector(".map-gesture-control");

        if (!controlCorner || !gestureControl || gestureControl.parentElement === controlCorner) {
            return;
        }

        gestureControl.classList.add("leaflet-control");
        controlCorner.appendChild(gestureControl);

        if (window.L && window.L.DomEvent) {
            window.L.DomEvent.disableClickPropagation(gestureControl);
            window.L.DomEvent.disableScrollPropagation(gestureControl);
        }
    }

    function updateMobileAvailability() {
        const isMobile = isMobileViewport();

        document.querySelectorAll(".map-gesture-control").forEach((control) => {
            control.hidden = isMobile;
            control.setAttribute("aria-hidden", isMobile ? "true" : "false");
        });

        if (isMobile) {
            setPanelOpen(false);
            if (isActive || isStarting || controller) {
                stopGestureControl();
            }
        }
    }

    function buttonLabel() {
        if (isStarting) {
            return "Starting hand gesture map control";
        }
        return isActive ? "Stop hand gesture map control" : "Start hand gesture map control";
    }

    function updateButtons() {
        const label = buttonLabel();
        const actionLabel = isStarting ? "Starting..." : isActive ? "Stop camera" : "Start camera";

        document.querySelectorAll(TOGGLE_SELECTOR).forEach((button) => {
            button.disabled = isStarting;
            button.classList.toggle("is-active", isActive);
            button.classList.toggle("is-starting", isStarting);
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
            button.setAttribute("aria-label", label);
            button.title = label;

            const icon = button.querySelector("i");
            if (icon) {
                icon.className = isActive ? "bi bi-stop-circle" : "bi bi-camera-video";
                icon.setAttribute("aria-hidden", "true");
            }

            const visibleLabel = button.querySelector(".map-gesture-action-label");
            if (visibleLabel) {
                visibleLabel.textContent = actionLabel;
            }
        });

        document.querySelectorAll(PANEL_TOGGLE_SELECTOR).forEach((button) => {
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-label", isActive ? "Open active hand gesture map control" : "Open hand gesture map control");

            const labelEl = button.querySelector(".map-gesture-panel-toggle__label");
            if (labelEl) {
                labelEl.textContent = isActive ? "Hand/gesture control on" : "Hand/gesture control";
            }
        });
    }

    function showStatus(message, timeoutMs) {
        const normalizedMessage = String(message || "");

        document.querySelectorAll(".map-gesture-control-status").forEach((statusEl) => {
            statusEl.textContent = normalizedMessage;
            statusEl.classList.toggle("has-message", normalizedMessage.length > 0);
        });

        if (statusTimer !== null) {
            clearTimeout(statusTimer);
            statusTimer = null;
        }

        if (normalizedMessage && timeoutMs) {
            statusTimer = setTimeout(() => {
                statusTimer = null;
                showStatus("", 0);
            }, timeoutMs);
        }
    }

    function setPanelOpen(isOpen) {
        document.querySelectorAll(PANEL_TOGGLE_SELECTOR).forEach((button) => {
            button.classList.toggle("is-active", isOpen);
            button.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });

        document.querySelectorAll(".map-gesture-panel").forEach((panel) => {
            panel.classList.toggle("is-open", isOpen);
            panel.hidden = !isOpen;
            panel.setAttribute("aria-hidden", isOpen ? "false" : "true");
        });
    }

    function togglePanel(event) {
        const button = event.target.closest(PANEL_TOGGLE_SELECTOR);
        if (!button) {
            return;
        }

        event.preventDefault();
        const isOpen = button.getAttribute("aria-expanded") === "true";
        setPanelOpen(!isOpen);
    }

    function closePanelFromOutsideClick(event) {
        if (
            event.target.closest(PANEL_TOGGLE_SELECTOR) ||
            event.target.closest(".map-gesture-panel")
        ) {
            return;
        }

        setPanelOpen(false);
    }

    function closePanelFromEscape(event) {
        if (event.key === "Escape") {
            setPanelOpen(false);
        }
    }

    function describeStartError(error) {
        const errorName = error && typeof error.name === "string" ? error.name : "";
        const isInsecureContext = !window.isSecureContext && !["localhost", "127.0.0.1"].includes(location.hostname);

        if (isInsecureContext) {
            return "Camera access requires HTTPS.";
        }
        if (errorName === "NotAllowedError" || errorName === "PermissionDeniedError") {
            return "Camera access was blocked.";
        }
        if (errorName === "NotFoundError" || errorName === "DevicesNotFoundError") {
            return "No camera was found.";
        }

        return "Gesture control could not start.";
    }

    function stopGestureControl(message) {
        if (controller) {
            try {
                controller.stop();
            } catch (error) {
                console.warn("Failed to stop map gesture control cleanly.", error);
            }
        }

        controller = null;
        isActive = false;
        isStarting = false;
        updateButtons();

        if (message) {
            showStatus(message, 2500);
        }
    }

    async function startGestureControl(targetMap) {
        if (isMobileViewport()) {
            setPanelOpen(false);
            return;
        }

        if (!isUsableMap(targetMap)) {
            showStatus("Map is still loading.", 2500);
            return;
        }

        const unsupportedReason = browserCanRunGestures();
        if (unsupportedReason) {
            showStatus(unsupportedReason, 5000);
            return;
        }

        isStarting = true;
        updateButtons();
        showStatus("Starting camera...", 0);

        try {
            const module = await loadGestureModule();
            const GestureMapController = module && module.GestureMapController;
            const container = targetMap.getContainer();

            if (targetMap !== leafletMap || !container || !container.isConnected) {
                throw new Error("Leaflet map changed before gesture control could start.");
            }
            if (typeof GestureMapController !== "function") {
                throw new Error("GestureMapController export was not found.");
            }

            controller = new GestureMapController({
                map: targetMap,
                webcam: {
                    width: 240,
                    height: 180,
                    margin: 16,
                    opacity: 0.85,
                },
                tuning: {
                    actionDwellMs: 90,
                    releaseGraceMs: 180,
                },
            });

            await controller.start();
            isActive = true;
            showStatus("Gesture control is on.", 2200);
        } catch (error) {
            console.error("Map gesture control failed to start.", error);
            stopGestureControl();
            showStatus(describeStartError(error), 5000);
            return;
        } finally {
            isStarting = false;
            updateButtons();
        }
    }

    async function toggleGestureControl(event) {
        const button = event.target.closest(TOGGLE_SELECTOR);
        if (!button) {
            return;
        }

        event.preventDefault();

        if (isStarting) {
            return;
        }

        if (isActive) {
            stopGestureControl("Gesture control is off.");
            return;
        }

        await startGestureControl(currentMap());
    }

    function setMap(nextMap) {
        if (!isUsableMap(nextMap)) {
            return;
        }

        if (leafletMap && leafletMap !== nextMap && (isActive || isStarting || controller)) {
            stopGestureControl();
        }

        leafletMap = nextMap;
        dockGestureControl(nextMap);
        updateMobileAvailability();
        updateButtons();
    }

    window.larentals = window.larentals || {};
    window.larentals.mapGestureControls = {
        setMap,
        stop: stopGestureControl,
        getMap: currentMap,
        load: loadGestureModule,
    };

    window.dash_props = Object.assign({}, window.dash_props, {
        module: Object.assign({}, window.dash_props && window.dash_props.module, {
            register_map_for_gesture_controls: function (event) {
                const mapFromEvent = event && event.target;
                setMap(mapFromEvent);
            },
        }),
    });

    document.addEventListener("click", toggleGestureControl);
    document.addEventListener("click", togglePanel);
    document.addEventListener("click", closePanelFromOutsideClick);
    document.addEventListener("keydown", closePanelFromEscape);
    mobileViewportQuery.addEventListener("change", updateMobileAvailability);
    window.addEventListener("pagehide", () => stopGestureControl());
    updateMobileAvailability();
    updateButtons();
})();
