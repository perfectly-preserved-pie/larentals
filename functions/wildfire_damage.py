import geopandas as gpd

# 2025 Palisades Fire: https://gis.data.ca.gov/datasets/CALFIRE-Forestry::dins-2025-palisades-public-view/about

def check_fire_damage(dins_geojson_path, lease_geojson_path, buy_geojson_path, buffer_distance=0.0001):
    # Load the GeoJSON files
    dins_gdf = gpd.read_file(dins_geojson_path)
    lease_gdf = gpd.read_file(lease_geojson_path)
    buy_gdf = gpd.read_file(buy_geojson_path)

    # Initialize the new column with False
    lease_gdf['affected_by_palisades_fire'] = False
    buy_gdf['affected_by_palisades_fire'] = False

    # Filter DINS GeoDataFrame to include only features with damage
    damaged_dins_gdf = dins_gdf[dins_gdf['DAMAGE'] != "No Damage"]

    # Create a buffer around the damaged points
    damaged_dins_gdf['geometry'] = damaged_dins_gdf.geometry.buffer(buffer_distance)

    # Perform spatial join with lease_gdf
    lease_gdf = gpd.sjoin(lease_gdf, damaged_dins_gdf[['geometry']], how='left', op='intersects')
    lease_gdf['affected_by_palisades_fire'] = lease_gdf['index_right'].notnull()
    lease_gdf.drop(columns=['index_right'], inplace=True)

    # Perform spatial join with buy_gdf
    buy_gdf = gpd.sjoin(buy_gdf, damaged_dins_gdf[['geometry']], how='left', op='intersects')
    buy_gdf['affected_by_palisades_fire'] = buy_gdf['index_right'].notnull()
    buy_gdf.drop(columns=['index_right'], inplace=True)

    # Print the number of affected properties
    print(f"Buffer distance: {buffer_distance}")
    print(f"Number of affected lease properties: {lease_gdf['affected_by_palisades_fire'].sum()}")
    print(f"Number of affected buy properties: {buy_gdf['affected_by_palisades_fire'].sum()}")

    return lease_gdf, buy_gdf

# Paths to the GeoJSON files
dins_geojson_path = 'assets/datasets/DINS_2025_Palisades_Public_View.geojson'
lease_geojson_path = 'assets/datasets/lease.geojson'
buy_geojson_path = 'assets/datasets/buy.geojson'

# Tune buffer distance
buffer_distance = 0.0001  # Adjust this value as needed

# Check fire damage and update DataFrames
lease_gdf, buy_gdf = check_fire_damage(dins_geojson_path, lease_geojson_path, buy_geojson_path, buffer_distance)

# Save the updated DataFrames back to GeoJSON files
lease_gdf.to_file(lease_geojson_path, driver='GeoJSON')
buy_gdf.to_file(buy_geojson_path, driver='GeoJSON')