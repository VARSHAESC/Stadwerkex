import pandas as pd
import numpy as np
import json
import os
import requests
import time
from scipy.spatial.distance import pdist, squareform
from scipy.sparse.csgraph import minimum_spanning_tree
import geo_utils

# File paths
BASE_DIR = r"c:\Users\ESC_LAP_RPA 2\EnergyBot_Offline"
GEOJSON_FILE = os.path.join(BASE_DIR, "excel_data", "utility_networks.geojson")

DEFAULT_LAT = 51.285
DEFAULT_LON = 7.051

# Define the 3 Entry Stations (supply points) for all utilities
STATIONS = {
    "Stadtnetz": [
        {"name": "Hammerstein", "lat": 51.2880, "lon": 7.0550, "capacity": "High"},
        {"name": "Kocherscheidt", "lat": 51.2810, "lon": 7.0450, "capacity": "Medium"}
    ],
    "Ortsteilnetz": [
        {"name": "Rohdenhaus", "lat": 51.2950, "lon": 7.0600, "capacity": "Low"}
    ]
}

UTILITIES = ["Gas", "Wasser", "Strom"]

def get_osrm_route(p1, p2):
    coords_str = f"{p1[0]},{p1[1]};{p2[0]},{p2[1]}"
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    try:
        for _ in range(2):
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "Ok":
                    return data["routes"][0]["geometry"]["coordinates"]
            time.sleep(1)
    except: pass
    return [p1, p2]

def build_network_mst(points):
    if len(points) <= 1: return []
    dist_matrix = squareform(pdist(np.array(points)))
    mst = minimum_spanning_tree(dist_matrix)
    cx = mst.tocoo()
    return [(points[i], points[j]) for i, j in zip(cx.row, cx.col)]

def offset_polyline(coords, offset_dist):
    """Offset a polyline by a perpendicular distance (in degrees approx)."""
    if offset_dist == 0 or len(coords) < 2:
        return coords
        
    new_coords = []
    for i in range(len(coords)):
        if i == 0:
            v1, v2 = np.array(coords[i]), np.array(coords[i+1])
        elif i == len(coords) - 1:
            v1, v2 = np.array(coords[i-1]), np.array(coords[i])
        else:
            v1, v2 = np.array(coords[i-1]), np.array(coords[i+1])
            
        direction = v2 - v1
        dist = np.linalg.norm(direction)
        if dist == 0:
            new_coords.append(coords[i])
            continue
            
        unit_direction = direction / dist
        perp = np.array([-unit_direction[1], unit_direction[0]])
        offset_pt = np.array(coords[i]) + perp * offset_dist
        new_coords.append(offset_pt.tolist())
    return new_coords

def create_utility_features(utility):
    print(f"Generating network for: {utility}")
    df = geo_utils.get_utility_df(utility)
    if df.empty: return []

    def assign_network(row):
        h_lat, h_lon = row['lat'], row['lon']
        if pd.isna(h_lat) or pd.isna(h_lon): return "Stadtnetz"
        min_dist_stadt = min([(h_lat - s['lat'])**2 + (h_lon - s['lon'])**2 for s in STATIONS["Stadtnetz"]])
        min_dist_ort = min([(h_lat - s['lat'])**2 + (h_lon - s['lon'])**2 for s in STATIONS["Ortsteilnetz"]])
        return "Stadtnetz" if min_dist_stadt < min_dist_ort else "Ortsteilnetz"
    
    df['network'] = df.apply(assign_network, axis=1)
    
    features = []
    OFFSET_MAP = {"Gas": -0.00004, "Wasser": 0.0, "Strom": 0.00004}
    offset_val = OFFSET_MAP.get(utility, 0)
    
    for network_name in ["Stadtnetz", "Ortsteilnetz"]:
        net_df = df[df['network'] == network_name].dropna(subset=['lat', 'lon'])
        if net_df.empty: continue
        
        net_houses_data = net_df[['lon', 'lat', 'Risiko']].to_dict('records')
        net_houses_pts = [[h['lon'], h['lat']] for h in net_houses_data]
        net_stations_pts = [[st['lon'], st['lat']] for st in STATIONS[network_name]]
        
        all_nodes = net_stations_pts + net_houses_pts
        if len(all_nodes) < 2: continue
        mst_edges = build_network_mst(all_nodes)
        
        for i, (p1, p2) in enumerate(mst_edges):
            route_coords = get_osrm_route(p1, p2)
            main_pipe_coords = offset_polyline(route_coords, offset_val)
            
            # Common properties to prevent Folium crash
            common_props = {
                "utility": utility,
                "network": network_name,
                "risiko": "N/A",
                "street": "N/A",
                "material": "N/A",
                "dimension": "N/A"
            }
            
            # 1. Main pipe
            main_props = common_props.copy()
            main_props.update({
                "type": "Main Pipe",
                "material": f"{utility} Main",
                "dimension": "DN 150" if utility != "Strom" else "110kV"
            })
            features.append({
                "type": "Feature",
                "properties": main_props,
                "geometry": {"type": "LineString", "coordinates": main_pipe_coords}
            })
            
            if len(main_pipe_coords) >= 2:
                for orig_pt, route_end in [(p1, main_pipe_coords[0]), (p2, main_pipe_coords[-1])]:
                    match = next((h for h in net_houses_data if h['lon'] == orig_pt[0] and h['lat'] == orig_pt[1]), None)
                    if match:
                        risk = match['Risiko']
                        lat_props = common_props.copy()
                        lat_props.update({
                            "type": "Lateral",
                            "risiko": risk,
                            "material": f"{utility} Connect",
                            "dimension": "DN 40" if utility != "Strom" else "400V"
                        })
                        features.append({
                            "type": "Feature",
                            "properties": lat_props,
                            "geometry": {"type": "LineString", "coordinates": [orig_pt, route_end]}
                        })
                        
                        node_props = common_props.copy()
                        node_props.update({
                            "type": "Node",
                            "risiko": risk # Nodes now carry risk for animation
                        })
                        features.append({
                            "type": "Feature",
                            "properties": node_props,
                            "geometry": {"type": "Point", "coordinates": route_end}
                        })
            if i % 20 == 0: print(f"  {utility} {network_name}: {i}/{len(mst_edges)}")
            
    return features

def main():
    all_features = []
    for util in UTILITIES:
        all_features.extend(create_utility_features(util))
        
    geojson = {"type": "FeatureCollection", "features": all_features}
    with open(GEOJSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    print(f"Generated {GEOJSON_FILE}")

if __name__ == "__main__":
    main()
