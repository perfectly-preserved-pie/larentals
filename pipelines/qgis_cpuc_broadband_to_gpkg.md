# QGIS workflow: downloading the CPUC broadband layer in QGIS and exporting to GeoPackage
---

## Open the GeoPackage

1. Launch **QGIS**.
2. **Layer → Add Layer → Add Vector Layer…**
3. In **Source**, select **File** and browse to your `.gpkg`.
4. Click **Add**.
5. In the list of layers inside the GeoPackage, select:
   - `ca_broadband_availability_aggregate` (or the closest match)
6. Click **Add** and then **Close**.
7. Right-click the layer in the **Layers** panel and add a filter.

   Example filter to show only Consumer broadband providers:
   ```
   Busconsm = 'Consumer'
   ```
8. Export the filtered layer to a new GeoPackage:
   1. Right-click the layer → **Export → Save Features As…**
   2. Format: **GeoPackage**
   3. File name: e.g., `cpuc_broadband_consumer.gpkg`
   4. Layer name: e.g., `cpuc_broadband_consumer`
   5. CRS: **EPSG:4326 - WGS 84**
   6. Click **OK**.
---

## 7) Validate a specific listing point against provider polygons

This is the key check for: “CPUC address tool shows 3 providers, but my join shows fewer.”

### Add your listing points as a point layer

If you can export listings to CSV with `longitude` and `latitude`:

1. **Layer → Add Layer → Add Delimited Text Layer…**
2. Select your CSV
3. Set:
   - X field = `longitude`
   - Y field = `latitude`
   - Geometry CRS = **EPSG:4326**
4. Click **Add**

### Zoom to the specific listing
1. Open the point layer attribute table
2. Search for the MLS number (e.g., `SR25012616MR`)
3. Select the row → **Zoom to Selection**

### Identify intersecting provider polygons
1. Select **Identify Features**
2. Click the listing point
3. In the Identify results, click intersecting broadband polygons and confirm:
   - `DBA`
   - `MaxAdDn` / `MaxAdUp`
   - `Service_Type` / `TechCode`

If you only see 1–2 providers here but CPUC shows 3:
- your point location likely differs from CPUC’s rooftop/address point, and/or
- some provider polygons don’t overlap the exact point.

That’s why buffering points by ~25–75m before intersecting often improves matches.

You can also just run this sqlite3 command against the GPKG to see which polygons intersect the listing point:

```bash
sqlite3 assets/datasets/larentals.db "
SELECT DBA, MaxAdDn, MaxAdUp, Service_Type
FROM lease_provider_options
WHERE listing_id = '25584589'
ORDER BY COALESCE(MaxAdDn,-1) DESC, COALESCE(MaxAdUp,-1) DESC, DBA ASC;
"
```