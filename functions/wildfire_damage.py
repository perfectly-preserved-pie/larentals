from typing import Tuple
import geopandas as gpd

# 2025 Palisades Fire: https://gis.data.ca.gov/datasets/CALFIRE-Forestry::dins-2025-palisades-public-view/about
# 2025 Eaton Fire: https://gis.data.ca.gov/datasets/CALFIRE-Forestry::eaton-2025-public-view/about

def check_fire_damage(palisades_geojson_path: str, eaton_geojson_path: str, lease_geojson_path: str, buy_geojson_path: str, buffer_distance: float = 10) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Checks for fire damage in lease and buy properties based on Palisades and Eaton fire datasets.

    Parameters:
    palisades_geojson_path (str): Path to the Palisades fire GeoJSON file.
    eaton_geojson_path (str): Path to the Eaton fire GeoJSON file.
    lease_geojson_path (str): Path to the lease properties GeoJSON file.
    buy_geojson_path (str): Path to the buy properties GeoJSON file.
    buffer_distance (float): Buffer distance for spatial join. Default is 10.

    Returns:
    Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]: Updated lease and buy GeoDataFrames with fire damage information.
    """
    # Load the GeoJSON files
    palisades_gdf = gpd.read_file(palisades_geojson_path)
    eaton_gdf = gpd.read_file(eaton_geojson_path)
    lease_gdf = gpd.read_file(lease_geojson_path)
    buy_gdf = gpd.read_file(buy_geojson_path)

    # Initialize the new columns with False
    lease_gdf['affected_by_palisades_fire'] = False
    lease_gdf['affected_by_eaton_fire'] = False
    buy_gdf['affected_by_palisades_fire'] = False
    buy_gdf['affected_by_eaton_fire'] = False

    # Filter GeoDataFrames to include only features with damage
    damaged_palisades_gdf = palisades_gdf[palisades_gdf['DAMAGE'] != "No Damage"]
    damaged_eaton_gdf = eaton_gdf[eaton_gdf['DAMAGE'] != "No Damage"]

    # Re-project to a projected CRS (e.g., EPSG:3857) for buffer operation
    damaged_palisades_gdf = damaged_palisades_gdf.to_crs(epsg=3857)
    damaged_eaton_gdf = damaged_eaton_gdf.to_crs(epsg=3857)
    lease_gdf = lease_gdf.to_crs(epsg=3857)
    buy_gdf = buy_gdf.to_crs(epsg=3857)

    # Create a buffer around the damaged points
    damaged_palisades_gdf['geometry'] = damaged_palisades_gdf.geometry.buffer(buffer_distance)
    damaged_eaton_gdf['geometry'] = damaged_eaton_gdf.geometry.buffer(buffer_distance)

    # Perform spatial join with lease_gdf for Palisades fire
    lease_gdf = gpd.sjoin(lease_gdf, damaged_palisades_gdf[['geometry']], how='left', predicate='intersects')
    lease_gdf['affected_by_palisades_fire'] = lease_gdf['index_right'].notnull()
    lease_gdf.drop(columns=['index_right'], inplace=True)

    # Perform spatial join with lease_gdf for Eaton fire
    lease_gdf = gpd.sjoin(lease_gdf, damaged_eaton_gdf[['geometry']], how='left', predicate='intersects')
    lease_gdf['affected_by_eaton_fire'] = lease_gdf['index_right'].notnull()
    lease_gdf.drop(columns=['index_right'], inplace=True)

    # Perform spatial join with buy_gdf for Palisades fire
    buy_gdf = gpd.sjoin(buy_gdf, damaged_palisades_gdf[['geometry']], how='left', predicate='intersects')
    buy_gdf['affected_by_palisades_fire'] = buy_gdf['index_right'].notnull()
    buy_gdf.drop(columns=['index_right'], inplace=True)

    # Perform spatial join with buy_gdf for Eaton fire
    buy_gdf = gpd.sjoin(buy_gdf, damaged_eaton_gdf[['geometry']], how='left', predicate='intersects')
    buy_gdf['affected_by_eaton_fire'] = buy_gdf['index_right'].notnull()
    buy_gdf.drop(columns=['index_right'], inplace=True)

    # Drop duplicates based on 'mls_number' and 'geometry'
    lease_gdf = lease_gdf.drop_duplicates(subset=['mls_number', 'geometry'])
    buy_gdf = buy_gdf.drop_duplicates(subset=['mls_number', 'geometry'])

    # Print the number of affected properties
    print(f"Buffer distance: {buffer_distance}")
    print(f"Number of affected lease properties by Palisades fire: {lease_gdf['affected_by_palisades_fire'].sum()}")
    print(f"Number of affected lease properties by Eaton fire: {lease_gdf['affected_by_eaton_fire'].sum()}")
    print(f"Number of affected buy properties by Palisades fire: {buy_gdf['affected_by_palisades_fire'].sum()}")
    print(f"Number of affected buy properties by Eaton fire: {buy_gdf['affected_by_eaton_fire'].sum()}")

    # Re-project back to the original CRS (EPSG:4326)
    lease_gdf = lease_gdf.to_crs(epsg=4326)
    buy_gdf = buy_gdf.to_crs(epsg=4326)

    return lease_gdf, buy_gdf

# Paths to the GeoJSON files
palisades_geojson_path = 'assets/datasets/DINS_2025_Palisades_Public_View.geojson'
eaton_geojson_path = 'assets/datasets/DINS_2025_Eaton_Public_View.geojson'
lease_geojson_path = 'assets/datasets/lease.geojson'
buy_geojson_path = 'assets/datasets/buy.geojson'

# Tune buffer distance
buffer_distance = 10  # Adjust this value as needed

# Check fire damage and update DataFrames
lease_gdf, buy_gdf = check_fire_damage(palisades_geojson_path, eaton_geojson_path, lease_geojson_path, buy_geojson_path, buffer_distance)

# Save the updated DataFrames back to GeoJSON files
lease_gdf.to_file(lease_geojson_path, driver='GeoJSON')
buy_gdf.to_file(buy_geojson_path, driver='GeoJSON')