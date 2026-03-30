# Self-Hosted Valhalla

This repo includes a sidecar Compose file for running Valhalla locally for the
commute filter.

The setup uses the official `ghcr.io/valhalla/valhalla-scripted:latest` image
and defaults to the Geofabrik Southern California extract so the graph stays
focused on the region this app cares about.

## Start the service

1. Create the host directories if you want them to exist before Docker binds them:

   ```bash
   mkdir -p docker/valhalla/custom_files docker/valhalla/gtfs_feeds
   ```

2. Put any GTFS feeds you want Valhalla to index into subfolders under
   `docker/valhalla/gtfs_feeds/`, for example:

   ```text
   docker/valhalla/gtfs_feeds/la_metro/
   docker/valhalla/gtfs_feeds/foothill_transit/
   ```

   Each agency directory should contain the unzipped GTFS `.txt` files.

3. Start Valhalla:

   ```bash
   docker compose -f docker-compose.valhalla.yml up -d
   ```

4. Watch the initial tile build:

   ```bash
   docker compose -f docker-compose.valhalla.yml logs -f valhalla
   ```

The first boot can take a while because the container downloads/builds graph
tiles, admins, and time zones. Transit builds also depend on the GTFS feeds
present in `docker/valhalla/gtfs_feeds/`.

## Point the app at the local service

If the Dash app is running on your host machine, set:

```bash
VALHALLA_BASE_URL=http://127.0.0.1:8002
VALHALLA_SERVICE_LABEL=Self-hosted Valhalla
VALHALLA_IS_PUBLIC_DEMO=False
VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES=400
VALHALLA_EXACT_COMMUTE_MAX_WORKERS=8
```

If the app is running in another container on the same Docker network, use:

```bash
VALHALLA_BASE_URL=http://valhalla:8002
```

`VALHALLA_EXACT_COMMUTE_MAX_CANDIDATES` is intentionally still capped. A
five-figure route burst on every filter change is expensive even on your own
box, so raise it gradually after you see how your host performs.

## Common rebuilds

If you add or replace GTFS feeds and want transit rebuilt from scratch:

```bash
VALHALLA_BUILD_TRANSIT=Force docker compose -f docker-compose.valhalla.yml up -d
```

If you want to force a full graph rebuild:

```bash
VALHALLA_FORCE_REBUILD=True docker compose -f docker-compose.valhalla.yml up -d
```
