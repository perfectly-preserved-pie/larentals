from dataclasses import dataclass
from dash import no_update
from dash_extensions.javascript import Namespace
from dotenv import load_dotenv
from loguru import logger
from typing import Any, ClassVar, Optional, Sequence, TypedDict, TypeAlias
import dash_leaflet as dl
import json
import time
import uuid

load_dotenv()

GeoJsonDict: TypeAlias = dict[str, Any]

class LazyLayerGeoJsonId(TypedDict):
    """
    Pattern-matching id payload for lazy-loaded optional GeoJSON layers.

    Attributes:
        type: Dash pattern-matching component type.
        page: Page key owning the layer, such as "lease" or "buy".
        layer: Internal layer key used to resolve its config.
    """
    type: str
    page: str
    layer: str

@dataclass(frozen=True)
class LayerConfig:
    """
    Declarative configuration for an optional or reusable GeoJSON overlay.

    Attributes:
        name: Display name shown in `dl.LayersControl`.
        dataset: Internal cache key for the loaded GeoJSON payload.
        filepath: On-disk path to the GeoJSON source file.
        point_to_layer: JavaScript namespace function used to render point features.
        cluster: Whether the layer should use Dash Leaflet marker clustering.
        zoom_to_bounds_on_click: Whether clicking a feature/cluster should fit its bounds.
        bubbling_mouse_events: Whether layer mouse events should bubble to the map.
        supercluster_options: Optional supercluster configuration passed to `dl.GeoJSON`.
    """
    name: str
    dataset: str
    filepath: str
    point_to_layer: str
    cluster: bool = True
    zoom_to_bounds_on_click: bool = True
    bubbling_mouse_events: bool = False
    supercluster_options: Optional[dict[str, Any]] = None

# Create a base class for the additional layers
# The additional layers are used in both the Lease and Sale pages, so we can use inheritance to avoid code duplication
class LayersClass:
    """
    Shared factory and lazy-loading helpers for optional map overlays.

    This class centralizes:
    - static overlay configuration
    - per-process GeoJSON caching
    - creation of `dl.GeoJSON` / `dl.Overlay` / `dl.LayersControl`
    - lazy resolution of layer data when users enable overlays
    """
    DEFAULT_SUPERCLUSTER_OPTIONS: ClassVar[dict[str, int]] = {
        'radius': 160,
        'maxClusterRadius': 40,
        'minZoom': 3,
    }
    LAYER_CONFIGS: ClassVar[dict[str, LayerConfig]] = {
        'oil_well': LayerConfig(
            name='Oil & Gas Wells',
            dataset='oil_well',
            filepath='assets/datasets/oil_well_optimized.geojson',
            point_to_layer='drawOilIcon',
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
        ),
        'crime': LayerConfig(
            name='Crime',
            dataset='crime',
            filepath='assets/datasets/crime.geojson',
            point_to_layer='drawCrimeIcon',
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
        ),
        'farmers_markets': LayerConfig(
            name='Farmers Markets',
            dataset='farmers_markets',
            filepath='assets/datasets/farmers_markets.geojson',
            point_to_layer='drawFarmersMarketIcon',
            bubbling_mouse_events=False,
            supercluster_options=DEFAULT_SUPERCLUSTER_OPTIONS,
        ),
    }
    geojson_cache: ClassVar[dict[str, GeoJsonDict]] = {}

    @classmethod
    def get_layer_config(cls, layer_key: str) -> LayerConfig:
        """
        Return the registered layer configuration for a given layer key.

        Args:
            layer_key: Internal layer identifier, such as `"farmers_markets"`.

        Returns:
            The corresponding `LayerConfig`.

        Raises:
            ValueError: If `layer_key` is not registered in `LAYER_CONFIGS`.
        """
        try:
            return cls.LAYER_CONFIGS[layer_key]
        except KeyError as exc:
            raise ValueError(
                f"Invalid layer_key: {layer_key}. Expected one of {sorted(cls.LAYER_CONFIGS)}."
            ) from exc

    @classmethod
    def load_geojson_data(cls, filepath: str, dataset: str) -> GeoJsonDict:
        """
        Load a GeoJSON payload from disk with simple per-process caching.

        Args:
            filepath: Path to the GeoJSON file on disk.
            dataset: Cache key used to store and retrieve the parsed payload.

        Returns:
            The parsed GeoJSON object.
        """
        cached_data = cls.geojson_cache.get(dataset)
        if cached_data is not None:
            logger.info(f"'{dataset}' dataset already loaded; skipping reload.")
            return cached_data

        start_time = time.time()
        with open(filepath, 'r') as f:
            loaded_data = json.load(f)

        cls.geojson_cache[dataset] = loaded_data
        duration = time.time() - start_time
        logger.info(f"Loaded '{dataset}' dataset in {duration:.2f} seconds.")
        return loaded_data

    @classmethod
    def create_geojson_layer(
        cls,
        layer_key: str,
        *,
        component_id: str | LazyLayerGeoJsonId | None = None,
        data: GeoJsonDict | None = None,
    ) -> dl.GeoJSON:
        """
        Build a `dl.GeoJSON` component from a registered layer config.

        Args:
            layer_key: Internal key identifying which layer config to use.
            component_id: Optional Dash component id. When omitted, a UUID is generated.
            data: Optional GeoJSON payload. Pass `None` to create a lazy placeholder layer.

        Returns:
            A configured `dl.GeoJSON` component.
        """
        spec = cls.get_layer_config(layer_key)
        ns = Namespace("myNamespace", "mySubNamespace")

        geojson_kwargs = dict(
            id=component_id if component_id is not None else str(uuid.uuid4()),
            data=data,
            cluster=spec.cluster,
            zoomToBoundsOnClick=spec.zoom_to_bounds_on_click,
            bubblingMouseEvents=spec.bubbling_mouse_events,
            pointToLayer=ns(spec.point_to_layer),
        )
        if spec.supercluster_options is not None:
            geojson_kwargs["superClusterOptions"] = dict(spec.supercluster_options)

        return dl.GeoJSON(**geojson_kwargs)

    @classmethod
    def lazy_layer_geojson_id(cls, page_key: str, layer_key: str) -> LazyLayerGeoJsonId:
        """
        Build a pattern-matching id for a lazy-loaded GeoJSON layer component.

        Args:
            page_key: Page identifier, such as `"lease"` or `"buy"`.
            layer_key: Internal layer identifier.

        Returns:
            A pattern-matching id dict suitable for Dash callbacks.
        """
        return {
            "type": "lazy-layer-geojson",
            "page": page_key,
            "layer": layer_key,
        }

    @classmethod
    def layers_control_id(cls, page_key: str) -> str:
        """
        Return the Dash id used by a page's `dl.LayersControl`.

        Args:
            page_key: Page identifier, such as `"lease"` or `"buy"`.

        Returns:
            A stable string id for the page's layer control.
        """
        return f"{page_key}-layers-control"

    @classmethod
    def create_lazy_overlay(
        cls,
        page_key: str,
        layer_key: str,
        *,
        checked: bool = False,
    ) -> dl.Overlay:
        """
        Create a lazy overlay wrapper for a registered layer.

        The returned overlay contains a `dl.GeoJSON` child with `data=None`.
        A callback can later populate the child when the overlay is enabled.

        Args:
            page_key: Page identifier owning the overlay.
            layer_key: Internal layer identifier.
            checked: Whether the overlay should be enabled by default.

        Returns:
            A `dl.Overlay` configured for lazy GeoJSON loading.
        """
        spec = cls.get_layer_config(layer_key)
        geojson_layer = cls.create_geojson_layer(
            layer_key,
            component_id=cls.lazy_layer_geojson_id(page_key, layer_key),
            data=None,
        )
        return dl.Overlay(
            geojson_layer,
            name=spec.name,
            checked=checked,
        )

    @classmethod
    def create_layers_control(
        cls,
        page_key: str,
        layer_keys: Sequence[str],
        *,
        checked_layer_keys: Sequence[str] = (),
    ) -> dl.LayersControl:
        """
        Create a `dl.LayersControl` for a page's optional overlays.

        Args:
            page_key: Page identifier owning the control.
            layer_keys: Ordered collection of registered layer keys to expose.
            checked_layer_keys: Subset of `layer_keys` that should start enabled.

        Returns:
            A populated `dl.LayersControl` containing lazy overlays.
        """
        checked_keys = set(checked_layer_keys)
        overlays = [
            cls.create_lazy_overlay(page_key, layer_key, checked=layer_key in checked_keys)
            for layer_key in layer_keys
        ]
        return dl.LayersControl(
            overlays,
            id=cls.layers_control_id(page_key),
            collapsed=True,
            position='topleft',
        )

    @classmethod
    def resolve_lazy_layer_data(
        cls,
        selected_overlays: Optional[Sequence[str]],
        layer_ids: Optional[Sequence[LazyLayerGeoJsonId]],
        current_data: Optional[Sequence[GeoJsonDict | None]],
    ) -> list[Any]:
        """
        Resolve which lazy overlay payloads should be loaded for a callback update.

        This helper is designed for a Dash callback whose output targets
        `({"type": "lazy-layer-geojson", ...}, "data")`.

        Args:
            selected_overlays: Names currently enabled in `dl.LayersControl.overlays`.
            layer_ids: Pattern-matching ids for the targeted GeoJSON components.
            current_data: Existing GeoJSON payloads for those components.

        Returns:
            A list aligned to `layer_ids`, containing either:
            - a newly loaded GeoJSON payload when the layer was enabled and not yet loaded
            - `no_update` when nothing should change for that output
        """
        if not layer_ids:
            return []

        selected_overlay_names = set(selected_overlays or [])
        existing_payloads = list(current_data or [])
        if len(existing_payloads) < len(layer_ids):
            existing_payloads.extend([None] * (len(layer_ids) - len(existing_payloads)))

        resolved_payloads: list[Any] = []
        for layer_id, existing_payload in zip(layer_ids, existing_payloads):
            layer_key = layer_id["layer"]
            spec = cls.get_layer_config(layer_key)

            if spec.name not in selected_overlay_names:
                resolved_payloads.append(no_update)
                continue

            if existing_payload is not None:
                resolved_payloads.append(no_update)
                continue

            resolved_payloads.append(
                cls.load_geojson_data(filepath=spec.filepath, dataset=spec.dataset)
            )

        return resolved_payloads

    @classmethod
    def create_oil_well_geojson_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded oil and gas wells GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for oil well data.
        """
        spec = cls.get_layer_config('oil_well')
        return cls.create_geojson_layer(
            'oil_well',
            data=cls.load_geojson_data(filepath=spec.filepath, dataset=spec.dataset),
        )
    
    @classmethod
    def create_farmers_markets_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded farmers markets GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for farmers market data.
        """
        spec = cls.get_layer_config('farmers_markets')
        return cls.create_geojson_layer(
            'farmers_markets',
            data=cls.load_geojson_data(filepath=spec.filepath, dataset=spec.dataset),
        )

    @classmethod
    def create_crime_layer(cls) -> dl.GeoJSON:
        """
        Create an eagerly loaded crime GeoJSON layer.

        Returns:
            A configured `dl.GeoJSON` component for crime data.
        """
        spec = cls.get_layer_config('crime')
        return cls.create_geojson_layer(
            'crime',
            data=cls.load_geojson_data(filepath=spec.filepath, dataset=spec.dataset),
        )
