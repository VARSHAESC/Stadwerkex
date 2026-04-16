import pandas as pd
import numpy as np
import json
import os
import requests
import time
from scipy.spatial.distance import pdist, squareform
from scipy.sparse.csgraph import minimum_spanning_tree

# File paths
BASE_DIR = r"c:\Users\ESC_LAP_RPA 2\EnergyBot_Offline"
EXCEL_FILE = os.path.join(BASE_DIR, "excel_data", "Hausanschluss_data.xlsx")
GEOJSON_FILE = os.path.join(BASE_DIR, "excel_data", "gas_pipelines.geojson")

DEFAULT_LAT = 51.285
DEFAULT_LON = 7.051

# Define the 3 Gas Entry Stations
STATIONS = [
    {"name": "Hammerstein", "lat": 51.2880, "lon": 7.0550, "network": "Stadtnetz", "capacity": "10,000 Nm³/h"},
    {"name": "Kocherscheidt", "lat": 51.2810, "lon": 7.0450, "network": "Stadtnetz", "capacity": "7,000 Nm³/h"},
    {"name": "Rohdenhaus", "lat": 51.2950, "lon": 7.0600, "network": "Ortsteilnetz", "capacity": "600 Nm³/h"}
]

def load_data():
    try:
        df = pd.read_excel(EXCEL_FILE)
    except Exception as e:
        print(f"Error loading Excel: {e}")
        return pd.DataFrame()
        
    df_gas = df.copy()
    
    if 'Breitengrad (Latitude)' in df_gas.columns:
        df_gas['lat'] = pd.to_numeric(df_gas['Breitengrad (Latitude)'], errors='coerce').fillna(DEFAULT_LAT)
    else:
        df_gas['lat'] = DEFAULT_LAT
        
    if 'Lngengrad (Longitude)' in df_gas.columns:
        df_gas['lon'] = pd.to_numeric(df_gas['Lngengrad (Longitude)'], errors='coerce').fillna(DEFAULT_LON)
    elif 'Längengrad (Longitude)' in df_gas.columns:
         df_gas['lon'] = pd.to_numeric(df_gas['Längengrad (Longitude)'], errors='coerce').fillna(DEFAULT_LON)
    else:
        df_gas['lon'] = DEFAULT_LON

    street_col = 'Straße' if 'Straße' in df_gas.columns else ('Strae' if 'Strae' in df_gas.columns else None)
    if street_col:
        df_gas['street_clean'] = df_gas[street_col].astype(str).str.strip()
    else:
         df_gas['street_clean'] = "Unknown Street"

    # Assign Network based on nearest station
    def assign_network(row):
        h_lat, h_lon = row['lat'], row['lon']
        min_dist = float('inf')
        assigned_net = "Stadtnetz"
        for st in STATIONS:
            d = (h_lat - st['lat'])**2 + (h_lon - st['lon'])**2
            if d < min_dist:
                min_dist = d
                assigned_net = st['network']
        return assigned_net
        
    df_gas['network'] = df_gas.apply(assign_network, axis=1)
    
    return df_gas

def get_osrm_route(p1, p2):
    """Get street-routed polyline between two points using OSRM"""
    coords_str = f"{p1[0]},{p1[1]};{p2[0]},{p2[1]}"
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson&continue_straight=true"
    
    try:
        # Retry logic for public API
        for _ in range(3):
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "Ok":
                    # Extract the actual street geometry
                    return data["routes"][0]["geometry"]["coordinates"]
            time.sleep(0.5)
    except Exception:
        pass
        
    # Fallback to straight line
    return [p1, p2]

def point_to_line_dist(pt, v, w):
    v = np.array(v)
    w = np.array(w)
    pt = np.array(pt)
    
    l2 = np.sum((w - v)**2)
    if l2 == 0.0:
        return np.linalg.norm(pt - v), v
        
    t = max(0, min(1, np.dot(pt - v, w - v) / l2))
    projection = v + t * (w - v)
    return np.linalg.norm(pt - projection), projection

def build_network_mst(points):
    """Build a Minimum Spanning Tree from a list of points (lon, lat) to ensure connectivity"""
    if len(points) <= 1:
        return []
        
    # Calculate pairwise distances
    pts_array = np.array(points)
    dist_matrix = squareform(pdist(pts_array))
    
    # Compute MST
    mst = minimum_spanning_tree(dist_matrix)
    
    # Extract edges from MST
    cx = mst.tocoo()
    edges = []
    for i, j, v in zip(cx.row, cx.col, cx.data):
        edges.append((points[i], points[j]))
        
    return edges

def create_geojson(df):
    features = []
    
    # Station Nodes removed from GeoJSON output as per user request
    pass

    # Group into the two networks: Stadtnetz (Hammerstein+Kocherscheidt) and Ortsteilnetz (Rohdenhaus)
    for network_name in ["Stadtnetz", "Ortsteilnetz"]:
        print(f"Building {network_name}...")
        
        # Get houses for this network
        net_houses = df[df['network'] == network_name][['lon', 'lat']].values.tolist()
        
        # Get stations for this network
        net_stations = [[st['lon'], st['lat']] for st in STATIONS if st['network'] == network_name]
        
        # All nodes in this graph
        all_nodes = net_stations + net_houses
        
        if len(all_nodes) < 2:
            continue
            
        # Build Minimum Spanning Tree to guarantee all houses are connected to the network
        mst_edges = build_network_mst(all_nodes)
        
        print(f"  Generated {len(mst_edges)} logical connections. Routing via streets...")
        
        for i, (p1, p2) in enumerate(mst_edges):
            # Route this connection via OSRM to follow the street
            route_coords = get_osrm_route(p1, p2)
            
            # The route returned is the main street pipe
            # However, if it's a house-to-house connection, the OSRM route might not start EXACTLY at the house 
            # (houses are off-street). OSRM snaps to the nearest road. 
            # We treat the OSRM route as the "Main Pipe" and draw "Lateral Pipes" from the house to the ends of the route.
            
            # 1. Main Pipe (The street route)
            features.append({
                "type": "Feature",
                "properties": {
                    "type": "Main Pipe",
                    "street": network_name, # Use network name as a placeholder for street on mains
                    "network": network_name,
                    "material": "PE-HD (Main)",
                    "dimension": "DN 150",
                    "utility": "Gas Pipeline"
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": route_coords
                }
            })
            
            # 2. Laterals and Nodes
            # If the original point p1 or p2 wasn't exactly on the route, draw a lateral to connect it.
            # OSRM endpoints are route_coords[0] and route_coords[-1]
            if len(route_coords) >= 2:
                for original_pt, route_end in [(p1, route_coords[0]), (p2, route_coords[-1])]:
                    dist = (original_pt[0]-route_end[0])**2 + (original_pt[1]-route_end[1])**2
                    if dist > 1e-10 and original_pt not in net_stations: # Don't draw laterals for stations
                        features.append({
                            "type": "Feature",
                            "properties": {
                                "type": "Lateral",
                                "street": "N/A",
                                "network": network_name,
                                "material": "PE-HD (Muffe)",
                                "dimension": "DN 40",
                                "utility": "Gas Pipeline"
                            },
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [original_pt, route_end]
                            }
                        })
                        
                        features.append({
                            "type": "Feature",
                            "properties": {
                                "type": "Node",
                                "street": "N/A",
                                "network": network_name,
                                "material": "N/A",
                                "dimension": "N/A",
                                "utility": "Gas Pipeline"
                            },
                            "geometry": {
                                "type": "Point",
                                "coordinates": route_end
                            }
                        })
            
            if i % 10 == 0:
                print(f"  Routed {i}/{len(mst_edges)} edges...")

    return {"type": "FeatureCollection", "features": features}

def main():
    print("Starting fully connected pipeline generation using MST and OSRM...")
    df = load_data()
    if df.empty:
        print("Dataframe is empty.")
        return
        
    geojson = create_geojson(df)
    with open(GEOJSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    print(f"Generated {GEOJSON_FILE} with connected networks.")

if __name__ == "__main__":
    main()
