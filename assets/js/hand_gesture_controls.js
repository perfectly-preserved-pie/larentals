(function() {
    "use strict";

    const MEDIAPIPE_MODULE_URL =
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22-rc.20250304/+esm";
    const MEDIAPIPE_WASM_URL =
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22-rc.20250304/wasm";
    const HAND_LANDMARKER_MODEL_URL =
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
    const VIDEO_WIDTH = 640;
    const VIDEO_HEIGHT = 480;
    const HAND_CONNECTIONS = [
        [0, 1], [1, 2], [2, 3], [3, 4],
        [0, 5], [5, 6], [6, 7], [7, 8],
        [5, 9], [9, 10], [10, 11], [11, 12],
        [9, 13], [13, 14], [14, 15], [15, 16],
        [13, 17], [17, 18], [18, 19], [19, 20],
        [0, 17],
    ];
    const LANDMARKS = {
        WRIST: 0,
        THUMB_TIP: 4,
        INDEX_FINGER_MCP: 5,
        INDEX_FINGER_PIP: 6,
        INDEX_FINGER_TIP: 8,
        MIDDLE_FINGER_MCP: 9,
        MIDDLE_FINGER_PIP: 10,
        MIDDLE_FINGER_TIP: 12,
        RING_FINGER_MCP: 13,
        RING_FINGER_PIP: 14,
        RING_FINGER_TIP: 16,
        PINKY_MCP: 17,
        PINKY_PIP: 18,
        PINKY_TIP: 20,
    };
    const DEFAULT_TUNING = {
        actionDwellMs: 160,
        releaseGraceMs: 220,
        panDeadzonePx: 5,
        zoomDeadzoneRatio: 0.005,
        smoothingAlpha: 0.4,
        minDetectionConfidence: 0.55,
        minTrackingConfidence: 0.55,
        minPresenceConfidence: 0.55,
        panScale: 2.15,
        zoomScale: 1.45,
    };

    const root = window.larentals = window.larentals || {};
    const runtime = root.handGestures = root.handGestures || {
        maps: [],
        modulePromise: null,
        leafletHookInstalled: false,
        uiObserver: null,
        pollHandle: null,
        activeController: null,
    };

    class EmaPoint {
        constructor(alpha) {
            this.alpha = alpha;
            this.value = null;
        }

        update(x, y) {
            if (this.value === null) {
                this.value = { x, y };
                return this.value;
            }

            this.value = {
                x: this.alpha * x + (1 - this.alpha) * this.value.x,
                y: this.alpha * y + (1 - this.alpha) * this.value.y,
            };
            return this.value;
        }

        reset() {
            this.value = null;
        }
    }

    class EmaScalar {
        constructor(alpha) {
            this.alpha = alpha;
            this.value = null;
        }

        update(nextValue) {
            if (this.value === null) {
                this.value = nextValue;
                return this.value;
            }

            this.value = this.alpha * nextValue + (1 - this.alpha) * this.value;
            return this.value;
        }

        reset() {
            this.value = null;
        }
    }

    class GestureStateMachine {
        constructor(tuning) {
            this.tuning = tuning;
            this.mode = "idle";
            this.actionDwell = null;
            this.releaseTimer = null;
            this.panSmoother = new EmaPoint(tuning.smoothingAlpha);
            this.zoomSmoother = new EmaScalar(tuning.smoothingAlpha);
            this.prevPanPosition = null;
            this.prevZoomY = null;
        }

        reset() {
            this.mode = "idle";
            this.actionDwell = null;
            this.releaseTimer = null;
            this.panSmoother.reset();
            this.zoomSmoother.reset();
            this.prevPanPosition = null;
            this.prevZoomY = null;
        }

        update(frame) {
            const now = frame.timestamp;
            const leftActive = isActiveHand(frame.leftHand);
            const rightActive = isActiveHand(frame.rightHand);
            let desiredMode = "idle";

            if (leftActive && rightActive) {
                desiredMode = this.mode === "idle" ? "zooming" : this.mode;
            } else if (rightActive) {
                desiredMode = "zooming";
            } else if (leftActive) {
                desiredMode = "panning";
            }

            if (this.mode === "idle") {
                if (desiredMode !== "idle") {
                    if (!this.actionDwell || this.actionDwell.mode !== desiredMode) {
                        this.actionDwell = { mode: desiredMode, startMs: now };
                    } else if (now - this.actionDwell.startMs >= this.tuning.actionDwellMs) {
                        this.transitionTo(desiredMode);
                    }
                } else {
                    this.actionDwell = null;
                }

                return { mode: this.mode, panDelta: null, zoomDelta: null };
            }

            if (this.mode === "panning") {
                if (desiredMode !== "panning") {
                    if (this.releaseTimer === null) {
                        this.releaseTimer = now;
                    } else if (now - this.releaseTimer >= this.tuning.releaseGraceMs) {
                        this.transitionTo("idle");
                    }
                    return { mode: this.mode, panDelta: null, zoomDelta: null };
                }

                this.releaseTimer = null;
                const hand = frame.leftHand;
                if (!hand || !isActiveHand(hand)) {
                    this.transitionTo("idle");
                    return { mode: this.mode, panDelta: null, zoomDelta: null };
                }

                const wrist = hand.landmarks[LANDMARKS.WRIST];
                const smooth = this.panSmoother.update(wrist.x, wrist.y);
                let panDelta = null;
                if (this.prevPanPosition !== null) {
                    const deltaX = smooth.x - this.prevPanPosition.x;
                    const deltaY = smooth.y - this.prevPanPosition.y;
                    const deadzone = this.tuning.panDeadzonePx / VIDEO_WIDTH;
                    if (Math.abs(deltaX) > deadzone || Math.abs(deltaY) > deadzone) {
                        panDelta = { x: deltaX, y: deltaY };
                    }
                }
                this.prevPanPosition = smooth;
                return { mode: this.mode, panDelta, zoomDelta: null };
            }

            if (this.mode === "zooming") {
                if (desiredMode !== "zooming") {
                    if (this.releaseTimer === null) {
                        this.releaseTimer = now;
                    } else if (now - this.releaseTimer >= this.tuning.releaseGraceMs) {
                        this.transitionTo("idle");
                    }
                    return { mode: this.mode, panDelta: null, zoomDelta: null };
                }

                this.releaseTimer = null;
                const hand = frame.rightHand;
                if (!hand || !isActiveHand(hand)) {
                    this.transitionTo("idle");
                    return { mode: this.mode, panDelta: null, zoomDelta: null };
                }

                const wrist = hand.landmarks[LANDMARKS.WRIST];
                const smoothY = this.zoomSmoother.update(wrist.y);
                let zoomDelta = null;
                if (this.prevZoomY !== null) {
                    const delta = smoothY - this.prevZoomY;
                    if (Math.abs(delta) > this.tuning.zoomDeadzoneRatio) {
                        zoomDelta = -delta;
                    }
                }
                this.prevZoomY = smoothY;
                return { mode: this.mode, panDelta: null, zoomDelta };
            }

            this.transitionTo("idle");
            return { mode: this.mode, panDelta: null, zoomDelta: null };
        }

        transitionTo(nextMode) {
            this.mode = nextMode;
            this.actionDwell = null;
            this.releaseTimer = null;
            if (nextMode !== "panning") {
                this.panSmoother.reset();
                this.prevPanPosition = null;
            }
            if (nextMode !== "zooming") {
                this.zoomSmoother.reset();
                this.prevZoomY = null;
            }
        }
    }

    class LeafletGestureController {
        constructor(map, panel) {
            this.map = map;
            this.panel = panel;
            this.running = false;
            this.mode = "idle";
            this.status = "Enable to start webcam-based pan and zoom.";
            this.lastFrame = null;
            this.lastVideoTime = -1;
            this.previewHidden = false;
            this.video = null;
            this.stream = null;
            this.canvas = null;
            this.ctx = null;
            this.badge = null;
            this.previewEl = null;
            this.rafHandle = null;
            this.landmarker = null;
            this.stateMachine = new GestureStateMachine(DEFAULT_TUNING);
            this.classifierState = {
                Left: { pinchActive: false },
                Right: { pinchActive: false },
            };
        }

        async start() {
            if (this.running) {
                return;
            }

            this.setUiState("loading", "Requesting webcam access…");
            try {
                if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
                    throw new Error("This browser does not support webcam access.");
                }

                const visionTasks = await loadVisionTasks();
                await this.initializeHandLandmarker(visionTasks);
                await this.initializeCamera();
                this.ensurePreview();
                this.running = true;
                this.mode = "idle";
                this.status = "Make a fist or pinch to begin.";
                this.loop();
                this.syncUi();
            } catch (error) {
                console.error("Failed to start hand controls.", error);
                this.stop({
                    keepStatus: true,
                    mode: "error",
                    status: error && error.message ? error.message : "Could not start hand controls.",
                });
            }
        }

        stop(options) {
            const keepStatus = !!(options && options.keepStatus);
            if (this.rafHandle !== null) {
                cancelAnimationFrame(this.rafHandle);
                this.rafHandle = null;
            }

            this.running = false;
            this.lastFrame = null;
            this.lastVideoTime = -1;
            this.mode = options && options.mode ? options.mode : "idle";
            this.status = keepStatus && options && options.status
                ? options.status
                : "Enable to start webcam-based pan and zoom.";

            this.stateMachine.reset();
            this.classifierState.Left.pinchActive = false;
            this.classifierState.Right.pinchActive = false;

            if (this.stream) {
                this.stream.getTracks().forEach(function(track) {
                    track.stop();
                });
            }
            this.stream = null;

            if (this.video) {
                this.video.srcObject = null;
            }

            if (this.landmarker && typeof this.landmarker.close === "function") {
                this.landmarker.close();
            }
            this.landmarker = null;

            if (this.previewEl && this.previewEl.parentElement) {
                this.previewEl.parentElement.removeChild(this.previewEl);
            }
            this.previewEl = null;
            this.canvas = null;
            this.ctx = null;
            this.badge = null;
            this.video = null;

            if (runtime.activeController === this) {
                runtime.activeController = null;
            }

            this.syncUi();
        }

        togglePreview() {
            this.previewHidden = !this.previewHidden;
            this.syncPreviewVisibility();
            this.syncUi();
        }

        loop() {
            if (!this.running) {
                return;
            }

            this.rafHandle = requestAnimationFrame(this.loop.bind(this));
            this.processFrame();
        }

        async initializeHandLandmarker(visionTasks) {
            const vision = await visionTasks.FilesetResolver.forVisionTasks(MEDIAPIPE_WASM_URL);
            try {
                this.landmarker = await visionTasks.HandLandmarker.createFromOptions(vision, {
                    baseOptions: {
                        modelAssetPath: HAND_LANDMARKER_MODEL_URL,
                        delegate: "GPU",
                    },
                    runningMode: "VIDEO",
                    numHands: 2,
                    minHandDetectionConfidence: DEFAULT_TUNING.minDetectionConfidence,
                    minTrackingConfidence: DEFAULT_TUNING.minTrackingConfidence,
                    minHandPresenceConfidence: DEFAULT_TUNING.minPresenceConfidence,
                });
            } catch (gpuError) {
                this.landmarker = await visionTasks.HandLandmarker.createFromOptions(vision, {
                    baseOptions: {
                        modelAssetPath: HAND_LANDMARKER_MODEL_URL,
                        delegate: "CPU",
                    },
                    runningMode: "VIDEO",
                    numHands: 2,
                    minHandDetectionConfidence: DEFAULT_TUNING.minDetectionConfidence,
                    minTrackingConfidence: DEFAULT_TUNING.minTrackingConfidence,
                    minHandPresenceConfidence: DEFAULT_TUNING.minPresenceConfidence,
                });
                console.warn("Falling back to CPU hand landmark detection.", gpuError);
            }
        }

        async initializeCamera() {
            this.video = document.createElement("video");
            this.video.autoplay = true;
            this.video.muted = true;
            this.video.playsInline = true;
            this.video.width = VIDEO_WIDTH;
            this.video.height = VIDEO_HEIGHT;

            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    width: VIDEO_WIDTH,
                    height: VIDEO_HEIGHT,
                    facingMode: "user",
                },
            });
            this.video.srcObject = this.stream;

            await new Promise((resolve) => {
                this.video.addEventListener("loadeddata", function handleLoadedData() {
                    resolve();
                }, { once: true });
            });
        }

        ensurePreview() {
            const mountPoint = this.map && this.map.getContainer
                ? this.map.getContainer().parentElement
                : null;
            if (!mountPoint || !this.video) {
                return;
            }

            this.previewEl = document.createElement("div");
            this.previewEl.className = "hand-gesture-preview hand-gesture-preview--visible";

            const surface = document.createElement("div");
            surface.className = "hand-gesture-preview__surface";

            this.badge = document.createElement("div");
            this.badge.className = "hand-gesture-preview__badge";
            this.badge.textContent = "Idle";

            const legend = document.createElement("div");
            legend.className = "hand-gesture-preview__legend";
            legend.innerHTML = "Left: pan<br>Right: zoom";

            this.canvas = document.createElement("canvas");
            this.canvas.className = "hand-gesture-preview__canvas";
            this.canvas.width = VIDEO_WIDTH;
            this.canvas.height = VIDEO_HEIGHT;
            this.ctx = this.canvas.getContext("2d");

            this.video.className = "hand-gesture-preview__video";
            this.video.setAttribute("aria-hidden", "true");

            surface.appendChild(this.video);
            surface.appendChild(this.canvas);
            surface.appendChild(this.badge);
            surface.appendChild(legend);
            this.previewEl.appendChild(surface);
            mountPoint.appendChild(this.previewEl);
            this.syncPreviewVisibility();
        }

        processFrame() {
            if (!this.video || !this.landmarker || this.video.readyState < 2) {
                return;
            }

            if (this.video.currentTime === this.lastVideoTime) {
                return;
            }
            this.lastVideoTime = this.video.currentTime;

            let result;
            try {
                result = this.landmarker.detectForVideo(this.video, performance.now());
            } catch (error) {
                console.error("Hand landmark detection failed.", error);
                return;
            }

            const frame = this.buildFrame(result);
            const output = this.stateMachine.update(frame);
            this.lastFrame = frame;
            this.mode = output.mode;
            this.status = buildStatusMessage(frame, output.mode);
            this.applyToMap(output);
            this.renderPreview(frame, output.mode);
            this.syncUi();
        }

        buildFrame(result) {
            const hands = [];
            const landmarkGroups = Array.isArray(result && result.landmarks) ? result.landmarks : [];
            for (let index = 0; index < landmarkGroups.length; index += 1) {
                const landmarks = landmarkGroups[index];
                const handednessGroup = result && Array.isArray(result.handedness)
                    ? result.handedness[index]
                    : null;
                const label = normalizeHandedness(handednessGroup);
                const score = handednessGroup && handednessGroup[0] && typeof handednessGroup[0].score === "number"
                    ? handednessGroup[0].score
                    : 0;
                const gesture = classifyGesture(landmarks, this.classifierState[label]);
                hands.push({
                    handedness: label,
                    score,
                    landmarks,
                    gesture,
                });
            }

            return {
                timestamp: performance.now(),
                hands,
                leftHand: hands.find(function(hand) {
                    return hand.handedness === "Left";
                }) || null,
                rightHand: hands.find(function(hand) {
                    return hand.handedness === "Right";
                }) || null,
            };
        }

        applyToMap(output) {
            if (!this.map) {
                return;
            }

            if (output.panDelta) {
                const size = this.map.getSize();
                if (size) {
                    const x = -output.panDelta.x * size.x * DEFAULT_TUNING.panScale;
                    const y = output.panDelta.y * size.y * DEFAULT_TUNING.panScale;
                    this.map.panBy([x, y], {
                        animate: false,
                        noMoveStart: true,
                    });
                }
            }

            if (typeof output.zoomDelta === "number" && Number.isFinite(output.zoomDelta)) {
                const currentZoom = this.map.getZoom();
                if (typeof currentZoom === "number") {
                    const mapSize = this.map.getSize();
                    const zoomPoint = mapSize
                        ? L.point(mapSize.x / 2, mapSize.y / 2)
                        : this.map.getCenter();
                    const nextZoom = clamp(
                        currentZoom + output.zoomDelta * DEFAULT_TUNING.zoomScale,
                        this.map.getMinZoom ? this.map.getMinZoom() : currentZoom - 3,
                        this.map.getMaxZoom ? this.map.getMaxZoom() : currentZoom + 3
                    );
                    this.map.setZoomAround(zoomPoint, nextZoom, {
                        animate: false,
                    });
                }
            }
        }

        renderPreview(frame, mode) {
            if (!this.ctx || !this.canvas) {
                return;
            }

            const context = this.ctx;
            const width = this.canvas.width;
            const height = this.canvas.height;
            context.clearRect(0, 0, width, height);

            if (!frame || !Array.isArray(frame.hands) || !frame.hands.length) {
                if (this.badge) {
                    this.badge.textContent = "Searching";
                }
                return;
            }

            frame.hands.forEach(function(hand) {
                drawHand(context, hand.landmarks, width, height, hand.gesture);
            });

            if (this.badge) {
                this.badge.textContent = mode === "idle" ? "Armed" : toTitleCase(mode);
            }
        }

        syncPreviewVisibility() {
            if (!this.previewEl) {
                return;
            }

            this.previewEl.classList.toggle("hand-gesture-preview--visible", !this.previewHidden && this.running);
            this.previewEl.classList.toggle("hand-gesture-preview--hidden", this.previewHidden || !this.running);
        }

        setUiState(mode, status) {
            this.mode = mode;
            this.status = status;
            this.syncUi();
        }

        syncUi() {
            if (!this.panel || !document.body.contains(this.panel)) {
                return;
            }

            const elements = getPanelElements(this.panel);
            const isActive = this.running;
            this.panel.classList.toggle("hand-gesture-panel--active", isActive);

            if (elements.toggleButton) {
                elements.toggleButton.textContent = isActive ? "Stop" : this.mode === "loading" ? "Starting…" : "Enable";
                elements.toggleButton.disabled = this.mode === "loading";
            }

            if (elements.previewToggle) {
                elements.previewToggle.textContent = this.previewHidden ? "Show preview" : "Hide preview";
                elements.previewToggle.disabled = !isActive;
            }

            if (elements.modeBadge) {
                const state = this.mode === "panning" || this.mode === "zooming"
                    ? this.mode
                    : this.mode === "loading"
                        ? "loading"
                        : this.mode === "error"
                            ? "error"
                            : "idle";
                elements.modeBadge.dataset.state = state;
                elements.modeBadge.textContent = this.mode === "loading"
                    ? "Loading"
                    : this.mode === "error"
                        ? "Error"
                        : this.mode === "idle"
                            ? "Idle"
                            : toTitleCase(this.mode);
            }

            if (elements.statusText) {
                elements.statusText.textContent = this.status;
            }

            this.syncPreviewVisibility();
        }
    }

    function loadVisionTasks() {
        if (!runtime.modulePromise) {
            runtime.modulePromise = import(MEDIAPIPE_MODULE_URL);
        }
        return runtime.modulePromise;
    }

    function installLeafletHook() {
        if (runtime.leafletHookInstalled || !window.L || !window.L.Map) {
            return false;
        }

        window.L.Map.addInitHook(function() {
            registerLeafletMap(this);
        });
        runtime.leafletHookInstalled = true;
        return true;
    }

    function registerLeafletMap(map) {
        if (!map || map.__larentalsHandGesturesRegistered) {
            return;
        }

        map.__larentalsHandGesturesRegistered = true;
        runtime.maps.push(map);
        map.on("unload", function() {
            runtime.maps = runtime.maps.filter(function(candidate) {
                return candidate !== map;
            });
            if (runtime.activeController && runtime.activeController.map === map) {
                runtime.activeController.stop();
            }
        });
    }

    function getActiveMap() {
        runtime.maps = runtime.maps.filter(function(map) {
            return map && map.getContainer && map.getContainer() && document.body.contains(map.getContainer());
        });

        for (let index = runtime.maps.length - 1; index >= 0; index -= 1) {
            const map = runtime.maps[index];
            const container = map.getContainer();
            if (container && container.id === "map") {
                return map;
            }
        }

        return runtime.maps.length ? runtime.maps[runtime.maps.length - 1] : null;
    }

    function getActivePanel() {
        return document.querySelector(".hand-gesture-panel");
    }

    function getPanelElements(panel) {
        return {
            toggleButton: panel.querySelector("[data-role='toggle']"),
            previewToggle: panel.querySelector("[data-role='preview-toggle']"),
            modeBadge: panel.querySelector("[data-role='mode']"),
            statusText: panel.querySelector("[data-role='status']"),
        };
    }

    function bindPanel(panel) {
        if (!panel || panel.dataset.handGesturesBound === "true") {
            return;
        }

        const elements = getPanelElements(panel);
        if (elements.toggleButton) {
            elements.toggleButton.addEventListener("click", function() {
                handleToggle(panel);
            });
        }

        if (elements.previewToggle) {
            elements.previewToggle.addEventListener("click", function() {
                const controller = runtime.activeController;
                if (controller && controller.panel === panel) {
                    controller.togglePreview();
                }
            });
        }

        panel.dataset.handGesturesBound = "true";
    }

    async function handleToggle(panel) {
        const activeController = runtime.activeController;
        if (activeController && activeController.panel === panel && activeController.running) {
            activeController.stop();
            return;
        }

        if (activeController) {
            activeController.stop();
        }

        const map = getActiveMap();
        if (!map) {
            setPanelMessage(panel, "error", "Map is still loading. Try again in a moment.");
            return;
        }

        const controller = new LeafletGestureController(map, panel);
        runtime.activeController = controller;
        controller.syncUi();
        await controller.start();
    }

    function setPanelMessage(panel, mode, status) {
        const elements = getPanelElements(panel);
        panel.classList.toggle("hand-gesture-panel--active", false);
        if (elements.toggleButton) {
            elements.toggleButton.textContent = "Enable";
            elements.toggleButton.disabled = false;
        }
        if (elements.previewToggle) {
            elements.previewToggle.disabled = true;
            elements.previewToggle.textContent = "Hide preview";
        }
        if (elements.modeBadge) {
            elements.modeBadge.dataset.state = mode;
            elements.modeBadge.textContent = mode === "error" ? "Error" : "Idle";
        }
        if (elements.statusText) {
            elements.statusText.textContent = status;
        }
    }

    function syncPanels() {
        const panel = getActivePanel();
        if (panel) {
            bindPanel(panel);
        }

        if (runtime.activeController && runtime.activeController.panel !== panel) {
            runtime.activeController.stop();
        } else if (runtime.activeController) {
            runtime.activeController.syncUi();
        }
    }

    function isActiveHand(hand) {
        return !!hand && (hand.gesture === "fist" || hand.gesture === "pinch");
    }

    function normalizeHandedness(handednessGroup) {
        const rawLabel = handednessGroup && handednessGroup[0] && handednessGroup[0].categoryName;
        return rawLabel === "Left" ? "Left" : "Right";
    }

    function classifyGesture(landmarks, classifierState) {
        if (!Array.isArray(landmarks) || landmarks.length < 21) {
            classifierState.pinchActive = false;
            return "none";
        }

        const handSize = getHandSize(landmarks);
        const pinchDistance = distance(
            landmarks[LANDMARKS.THUMB_TIP],
            landmarks[LANDMARKS.INDEX_FINGER_TIP]
        );
        const pinchEnter = handSize * 0.34;
        const pinchExit = handSize * 0.44;

        if (classifierState.pinchActive) {
            classifierState.pinchActive = pinchDistance < pinchExit;
        } else {
            classifierState.pinchActive = pinchDistance < pinchEnter;
        }

        if (classifierState.pinchActive) {
            return "pinch";
        }

        const fingerDefinitions = [
            [LANDMARKS.INDEX_FINGER_TIP, LANDMARKS.INDEX_FINGER_PIP, LANDMARKS.INDEX_FINGER_MCP],
            [LANDMARKS.MIDDLE_FINGER_TIP, LANDMARKS.MIDDLE_FINGER_PIP, LANDMARKS.MIDDLE_FINGER_MCP],
            [LANDMARKS.RING_FINGER_TIP, LANDMARKS.RING_FINGER_PIP, LANDMARKS.RING_FINGER_MCP],
            [LANDMARKS.PINKY_TIP, LANDMARKS.PINKY_PIP, LANDMARKS.PINKY_MCP],
        ];
        let curledFingers = 0;
        let extendedFingers = 0;

        fingerDefinitions.forEach(function(indices) {
            const extensionScore = getFingerExtensionScore(landmarks, indices[0], indices[1], indices[2]);
            if (extensionScore < handSize * 0.05) {
                curledFingers += 1;
            }
            if (extensionScore > handSize * 0.2) {
                extendedFingers += 1;
            }
        });

        if (curledFingers >= 3) {
            return "fist";
        }
        if (extendedFingers >= 3) {
            return "openPalm";
        }
        return "none";
    }

    function buildStatusMessage(frame, mode) {
        if (!frame || !frame.hands.length) {
            return "No hands detected yet. Raise one hand inside the preview box.";
        }

        if (frame.leftHand && frame.rightHand && isActiveHand(frame.leftHand) && isActiveHand(frame.rightHand) && mode === "idle") {
            return "Use one active hand at a time. Left pans, right zooms.";
        }

        if (mode === "panning") {
            return "Left hand active. Move gently to pan the map.";
        }

        if (mode === "zooming") {
            return "Right hand active. Move up or down to zoom.";
        }

        if (frame.leftHand && isActiveHand(frame.leftHand)) {
            return "Left hand seen. Hold that gesture for a beat to arm panning.";
        }

        if (frame.rightHand && isActiveHand(frame.rightHand)) {
            return "Right hand seen. Hold that gesture for a beat to arm zooming.";
        }

        return "Make a fist or pinch to begin. Left pans, right zooms.";
    }

    function getHandSize(landmarks) {
        const palmWidth = distance(
            landmarks[LANDMARKS.INDEX_FINGER_MCP],
            landmarks[LANDMARKS.PINKY_MCP]
        );
        const palmLength = distance(
            landmarks[LANDMARKS.WRIST],
            landmarks[LANDMARKS.MIDDLE_FINGER_MCP]
        );
        return Math.max(palmWidth, palmLength, 0.01);
    }

    function getFingerExtensionScore(landmarks, tipIndex, pipIndex, mcpIndex) {
        const wrist = landmarks[LANDMARKS.WRIST];
        const tip = landmarks[tipIndex];
        const pip = landmarks[pipIndex];
        const mcp = landmarks[mcpIndex];
        const tipDistance = distance(tip, wrist);
        const pipDistance = distance(pip, wrist);
        const mcpDistance = distance(mcp, wrist);
        return tipDistance - Math.max(pipDistance, mcpDistance);
    }

    function drawHand(context, landmarks, width, height, gesture) {
        const strokeStyle = gesture === "pinch"
            ? "rgba(245, 158, 11, 0.95)"
            : gesture === "fist"
                ? "rgba(34, 197, 94, 0.95)"
                : "rgba(96, 165, 250, 0.95)";
        const fillStyle = gesture === "pinch"
            ? "rgba(251, 191, 36, 0.95)"
            : gesture === "fist"
                ? "rgba(74, 222, 128, 0.95)"
                : "rgba(191, 219, 254, 0.92)";

        context.save();
        context.lineWidth = 4;
        context.lineCap = "round";
        context.lineJoin = "round";

        HAND_CONNECTIONS.forEach(function(pair) {
            const start = landmarks[pair[0]];
            const end = landmarks[pair[1]];
            if (!start || !end) {
                return;
            }

            context.beginPath();
            context.strokeStyle = strokeStyle;
            context.moveTo((1 - start.x) * width, start.y * height);
            context.lineTo((1 - end.x) * width, end.y * height);
            context.stroke();
        });

        landmarks.forEach(function(point) {
            context.beginPath();
            context.fillStyle = fillStyle;
            context.arc((1 - point.x) * width, point.y * height, 5, 0, Math.PI * 2);
            context.fill();
        });
        context.restore();
    }

    function distance(a, b) {
        if (!a || !b) {
            return 0;
        }
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        return Math.sqrt(dx * dx + dy * dy);
    }

    function clamp(value, minValue, maxValue) {
        return Math.max(minValue, Math.min(maxValue, value));
    }

    function toTitleCase(value) {
        return String(value || "")
            .replace(/([A-Z])/g, " $1")
            .replace(/^./, function(char) {
                return char.toUpperCase();
            })
            .trim();
    }

    function startLifecycle() {
        syncPanels();
        if (!runtime.uiObserver) {
            runtime.uiObserver = new MutationObserver(function() {
                syncPanels();
            });
            runtime.uiObserver.observe(document.body, {
                childList: true,
                subtree: true,
            });
        }

        if (!installLeafletHook() && runtime.pollHandle === null) {
            runtime.pollHandle = window.setInterval(function() {
                if (installLeafletHook()) {
                    window.clearInterval(runtime.pollHandle);
                    runtime.pollHandle = null;
                }
            }, 150);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", startLifecycle, { once: true });
    } else {
        startLifecycle();
    }
})();
