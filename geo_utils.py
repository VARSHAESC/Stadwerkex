# -*- coding: utf-8 -*-
"""
geo_utils.py — Data loader and geospatial utilities.
"""

import os
import re
import json
import pandas as pd
import numpy as np
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
EXCEL_FILE = os.path.join(BASE_DIR, "excel_data", "Hausanschluss_data.xlsx")
DEFAULT_EXCEL_PATH = EXCEL_FILE # Alias for compatibility
GEO_CACHE_FILE = os.path.join(BASE_DIR, "cache", "geo_cache.json")
ALL_UTILITIES = ["Gas", "Wasser"]
CSV_FILES = {u: EXCEL_FILE for u in ALL_UTILITIES}

MATERIAL_LIFESPAN = {
    "PE-HD": 50, "PE": 50, "PE100": 50, "PVC": 40,
    "Kupfer": 60, "Stahl": 65, "Grauguss": 80, "Duktilguss": 80,
    "Gusseisen": 80, "Kunststoff": 40, "HDPE": 50,
}

RISK_LADDER = {
    "Gas": [
        {"material": "Stahl mit KKS", "gut": 59, "mittel": 95, "life": 80},
        {"material": "Stahl ohne KKS", "gut": 51, "mittel": 83, "life": 70},
        {"material": "Stahl", "gut": 51, "mittel": 83, "life": 70}, # Fallback if KKS not specified
        {"material": "PE", "gut": 55, "mittel": 89, "life": 75},
    ],
    "Wasser": [
        {"material": "Asbestzement-(AZ)", "gut": 38, "mittel": 59, "life": 50},
        {"material": "Asbest", "gut": 38, "mittel": 59, "life": 50},
        {"material": "AZ", "gut": 38, "mittel": 59, "life": 50},
        {"material": "PE", "gut": 62, "mittel": 101, "life": 85},
        {"material": "PVC", "gut": 36, "mittel": 59, "life": 50},
        {"material": "Stahl", "gut": 44, "mittel": 71, "life": 60},
    ]
}

def _get_risk_profile(sparte: str, material: str):
    material_lower = str(material).lower()
    if sparte in RISK_LADDER:
        for profile in RISK_LADDER[sparte]:
            if profile["material"].lower() in material_lower:
                return profile
    return None

CURRENT_YEAR = datetime.now().year

def _fix_encoding(s: str) -> str:
    """Clean up strings from Excel artifacts."""
    if not isinstance(s, str): return str(s)
    s = s.replace('\ufffd', 'ü').replace('\u00fc', 'ü')
    s = s.replace('\u00e4', 'ä').replace('\u00f6', 'ö').replace('\u00df', 'ß')
    s = s.replace('\x00', '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def _parse_date(val) -> pd.Timestamp:
    if pd.isna(val): return pd.NaT
    if isinstance(val, datetime): return pd.Timestamp(val)
    s = str(val).strip()
    if not s or s.lower() == "nan": return pd.NaT
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try: return pd.to_datetime(s, format=fmt)
        except: pass
    return pd.NaT

def _infer_risk(row: pd.Series, sparte: str) -> str:
    age = row.get("Alter", 0)
    material = str(row.get("Werkstoff", "")).strip()
    if not age or pd.isna(age): return "Unbekannt"
    age = float(age)

    # Use granular risk ladder if available
    profile = _get_risk_profile(sparte, material)
    if profile:
        if age <= profile["gut"]: return "Niedrig"
        elif age <= profile["mittel"]: return "Mittel"
        else: return "Hoch"

    # Fallback to general logic
    lifespan = MATERIAL_LIFESPAN.get(material, 50)
    pct = age / lifespan
    if pct >= 0.85: return "Hoch"
    if pct >= 0.65: return "Mittel"
    return "Niedrig"

def _erneuerung_jahr(row: pd.Series, sparte: str) -> object:
    einbau = row.get("Einbaudatum", pd.NaT)
    material = str(row.get("Werkstoff", "")).strip()
    if pd.isna(einbau): return None
    
    profile = _get_risk_profile(sparte, material)
    lifespan = profile["life"] if profile else MATERIAL_LIFESPAN.get(material, 50)
    
    try: return int(einbau.year + lifespan)
    except: return None

def _docs_complete(row: pd.Series) -> str:
    doc_cols = [c for c in row.index if any(k in str(c).lower() for k in ["gestattung", "auftrag", "anfrage"])]
    if not doc_cols: return "Vollständig"
    missing = [c for c in doc_cols if pd.isna(row[c])]
    return "Lückenhaft" if missing else "Vollständig"

def _is_unsuitable_infrastructure(row: pd.Series, sparte: str) -> bool:
    """Checks if infrastructure needs modernization based purely on technical life table."""
    age = row.get("Alter", 0)
    if not age or pd.isna(age): return False
    
    material = str(row.get("Werkstoff", "")).strip()
    profile = _get_risk_profile(sparte, material)
    
    lifespan = profile["life"] if profile else MATERIAL_LIFESPAN.get(material, 50)
    return float(age) > lifespan

# ── Geodata logic ──────────────────────────────────────────────────────
def get_coordinates(row: pd.Series) -> tuple:
    """Gets coordinates from new explicit columns or UTM fallback."""
    # Find columns by keyword to be robust against encoding issues (e.g. Längengrad vs Lngengrad)
    lat_col = next((c for c in row.index if "Latitude" in str(c)), None)
    lon_col = next((c for c in row.index if "Longitude" in str(c)), None)
    
    lat = row.get(lat_col) if lat_col else None
    lon = row.get(lon_col) if lon_col else None
    
    # Check if they are valid numbers
    try:
        if pd.notna(lat) and pd.notna(lon):
            return float(lat), float(lon)
    except: pass

    # Fallback to UTM (Hochwert/Rechtswert) if they look like UTM
    hw = row.get("Hochwert Objekt")
    rw = row.get("Rechtswert Objekt")
    if pd.notna(hw) and pd.notna(rw) and rw < 2000000:
        # Transformation for UTM Zone 32N / Germany
        lat_calc = 48.0 + (hw - 5300000) / 111111
        lon_calc = 9.0 + (rw - 500000) / (111111 * 0.65)
        return lat_calc, lon_calc
    
    return None, None

def load_excel(path=EXCEL_FILE, header=0):
    if not os.path.exists(path): return pd.DataFrame()
    return pd.read_excel(path, header=header)

def get_utility_df(utility: str) -> pd.DataFrame:
    if not os.path.exists(EXCEL_FILE): return pd.DataFrame()
    try:
        raw = pd.read_excel(EXCEL_FILE, header=0)
    except: return pd.DataFrame()
    
    # Identify utility-specific columns
    common_cols = []
    util_cols = []
    for c in raw.columns:
        c_s = str(c).strip()
        c_l = c_s.lower()
        if c_l.startswith(utility.lower()):
            util_cols.append(c)
        elif not any(c_l.startswith(u.lower()) for u in ALL_UTILITIES):
            common_cols.append(c)
            
    if not util_cols: return pd.DataFrame()
    
    df = raw[common_cols + util_cols].copy()
    
    # ── Filter rows where the customer has NO connection for this utility ──
    # A row is excluded if ALL utility-specific columns are blank (NaN) or
    # explicitly set to "NA" / "N/A" (case-insensitive).
    def _is_na_value(v):
        if pd.isna(v): return True
        if isinstance(v, str) and v.strip().upper() in ("NA", "N/A", "N.A.", "-"): return True
        return False

    util_cols_in_df = [c for c in util_cols if c in df.columns]
    has_connection = df[util_cols_in_df].apply(
        lambda row: not all(_is_na_value(v) for v in row), axis=1
    )
    df = df[has_connection].copy()
    if df.empty: return pd.DataFrame()
    
    # Cleaning column names
    new_cols = []
    for c in df.columns:
        c_clean = str(c).strip()
        if c_clean.lower().startswith(utility.lower()):
            c_clean = c_clean[len(utility):].strip()
        c_clean = _fix_encoding(c_clean)
        new_cols.append(c_clean)
    df.columns = new_cols
    
    # Rename for consistency
    renames = {
        "Kundenname": "Kundenname",
        "Kunden Name": "Kundenname",
        "Objekt-ID (Nummer bspw.)": "Kundennummer",
        "Objekt-ID": "Kundennummer",
        "Einbaudatum/ Fertigmeldung": "Einbaudatum",
        "Werkstoff Anschlussleitung": "Werkstoff",
        "Werkstoff Anschlussleitung ": "Werkstoff",
        "Kabeltyp AL": "Werkstoff",
        "Dimension Anschlussleitung": "Dimension",
        "Querschnitt AL": "Dimension",
        "Strae": "Straße", "Strasse": "Straße",
        "Anschlusslänge Hausanschluss": "Länge",
        "Länge Anschlussleitung": "Länge",
    }
    
    final_cols = []
    for c in df.columns:
        found = False
        # Prioritize exact or more specific matches
        for k, v in renames.items():
            if k == c: # Exact match
                final_cols.append(v); found = True; break
        
        if not found:
            for k, v in renames.items():
                if k in c and v not in final_cols: # Substring match (fallback)
                    final_cols.append(v); found = True; break
        
        if not found: final_cols.append(c)
    df.columns = final_cols
    
    df["Sparte"] = utility
    
    # Extract coordinates
    coords = df.apply(get_coordinates, axis=1)
    df["lat"] = coords.apply(lambda x: x[0])
    df["lon"] = coords.apply(lambda x: x[1])

    if "Einbaudatum" in df.columns:
        df["Einbaudatum"] = df["Einbaudatum"].apply(_parse_date)
        df["Einbaujahr"] = df["Einbaudatum"].dt.year
        df["Alter"] = df["Einbaujahr"].apply(lambda y: CURRENT_YEAR - y if pd.notna(y) else 0)
    
    df["Risiko"] = df.apply(lambda r: _infer_risk(r, utility), axis=1)
    df["Erneuerung_empfohlen_bis"] = df.apply(lambda r: _erneuerung_jahr(r, utility), axis=1)
    df["Dokumente"] = df.apply(_docs_complete, axis=1)
    df["Infrastruktur_ungeeignet"] = df.apply(lambda r: _is_unsuitable_infrastructure(r, utility), axis=1)
    
    # Ensure key display columns are strings to prevent ArrowTypeError in Streamlit
    for col in ["Hausnummer", "Kundennummer", "Straße"]:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("nan", "")

    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    return df

def get_unified_df() -> pd.DataFrame:
    dfs = [get_utility_df(u) for u in ALL_UTILITIES]
    valid_dfs = [d for d in dfs if not d.empty]
    if not valid_dfs: return pd.DataFrame()
    return pd.concat(valid_dfs, ignore_index=True)

def kpi_advanced(df: pd.DataFrame) -> dict:
    if df.empty: return {k: 0 for k in ["total", "critical", "aging_30", "aging_40", "renewal_soon", "unsuitable", "over_lifespan"]}
    total = len(df)
    critical = int(df["Risiko"].eq("Hoch").sum())
    aging_30 = int(df["Alter"].ge(30).sum()) if "Alter" in df.columns else 0
    aging_40 = int(df["Alter"].ge(40).sum()) if "Alter" in df.columns else 0
    missing_docs = int(df["Dokumente"].eq("Lückenhaft").sum())
    unsuitable = int(df.get("Infrastruktur_ungeeignet", pd.Series([0]*total)).sum())
    over_lifespan = int((df["Erneuerung_empfohlen_bis"] < CURRENT_YEAR).sum()) if "Erneuerung_empfohlen_bis" in df.columns else 0
    return {
        "total": total, "critical": critical, "aging_30": aging_30, "aging_40": aging_40,
        "missing_docs": missing_docs, "doc_complete_pct": round(100*(total-missing_docs)/max(total,1), 1),
        "unsuitable": unsuitable,
        "avg_age": df["Alter"].mean() if "Alter" in df.columns else 0,
        "high_risk_pct": round(100 * critical / max(total, 1), 1),
        "renewal_soon": int(df["Erneuerung_empfohlen_bis"].dropna().apply(lambda x: x <= CURRENT_YEAR + 10).sum()) if "Erneuerung_empfohlen_bis" in df.columns else 0,
        "over_lifespan": over_lifespan
    }

def get_material_distribution(df: pd.DataFrame):
    if "Werkstoff" not in df.columns or "Einbaujahr" not in df.columns: return pd.DataFrame()
    return df.groupby(["Einbaujahr", "Werkstoff"]).size().reset_index(name="count")

def get_bundling_potential(df: pd.DataFrame):
    if "Straße" not in df.columns: return pd.DataFrame()
    critical_streets = df[df["Alter"] > 35].groupby("Straße").agg({"Alter": "mean", "Sparte": "count"}).rename(columns={"Sparte": "Anzahl"})
    return critical_streets.sort_values("Anzahl", ascending=False).head(10)

def invalidate_cache():
    import streamlit as st
    st.cache_data.clear()
    st.cache_resource.clear()

# ── Dynamic GeoJSON Regeneration ─────────────────────────────────────────
GEOJSON_FILE = os.path.join(BASE_DIR, "excel_data", "utility_networks.geojson")

OSRM_AVAILABLE = None

def check_osrm_available():
    global OSRM_AVAILABLE
    if OSRM_AVAILABLE is not None:
        return OSRM_AVAILABLE
    import os, requests
    base_url = os.environ.get("OSRM_BASE_URL", "http://localhost:5000")
    try:
        requests.get(f"{base_url}/route/v1/driving/0,0;0,0", timeout=1)
        OSRM_AVAILABLE = True
    except Exception:
        # Auto-fallback for local Python vs Docker routing (e.g. env says osrm:5000 but we are outside docker)
        try:
            requests.get("http://localhost:5000/route/v1/driving/0,0;0,0", timeout=1)
            os.environ["OSRM_BASE_URL"] = "http://localhost:5000"
            OSRM_AVAILABLE = True
        except Exception:
            OSRM_AVAILABLE = False
    return OSRM_AVAILABLE

# Entry stations (supply points) for the network topology
_STATIONS = {
    "Stadtnetz": [
        {"name": "Hammerstein",  "lat": 51.2880, "lon": 7.0550},
        {"name": "Kocherscheidt","lat": 51.2810, "lon": 7.0450},
    ],
    "Ortsteilnetz": [
        {"name": "Rohdenhaus", "lat": 51.2950, "lon": 7.0600},
    ]
}

def is_geojson_stale() -> bool:
    """Return True if the GeoJSON is missing or older than the Excel file."""
    if not os.path.exists(GEOJSON_FILE):
        return True
    if not os.path.exists(EXCEL_FILE):
        return False
    return os.path.getmtime(EXCEL_FILE) > os.path.getmtime(GEOJSON_FILE)

def _osrm_route(p1, p2):
    if not check_osrm_available():
        return [p1, p2]
    
    import requests, time as _time
    import os
    base_url = os.environ.get("OSRM_BASE_URL", "http://localhost:5000")
    coords = f"{p1[0]},{p1[1]};{p2[0]},{p2[1]}"
    url = (f"{base_url}/route/v1/driving/{coords}"
           f"?overview=full&geometries=geojson")
    try:
        for _ in range(2):
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                d = r.json()
                if d.get("code") == "Ok":
                    return d["routes"][0]["geometry"]["coordinates"]
            _time.sleep(0.5)
    except Exception as e:
        pass
    return [p1, p2]   # straight-line fallback

def _build_mst_edges(points):
    """Return edges of the Minimum Spanning Tree for the given list of [lon,lat] points."""
    from scipy.spatial.distance import pdist, squareform
    from scipy.sparse.csgraph import minimum_spanning_tree
    if len(points) < 2:
        return []
    arr = np.array(points)
    mst = minimum_spanning_tree(squareform(pdist(arr)))
    cx = mst.tocoo()
    return [(points[i], points[j]) for i, j in zip(cx.row, cx.col)]

def _offset_polyline(coords, offset_dist):
    """Shift a polyline perpendicularly by offset_dist degrees (approx)."""
    if offset_dist == 0 or len(coords) < 2:
        return coords
    out = []
    for i in range(len(coords)):
        if i == 0:
            v1, v2 = np.array(coords[i]), np.array(coords[i + 1])
        elif i == len(coords) - 1:
            v1, v2 = np.array(coords[i - 1]), np.array(coords[i])
        else:
            v1, v2 = np.array(coords[i - 1]), np.array(coords[i + 1])
        direction = v2 - v1
        dist = np.linalg.norm(direction)
        if dist == 0:
            out.append(coords[i])
            continue
        perp = np.array([-direction[1], direction[0]]) / dist
        out.append((np.array(coords[i]) + perp * offset_dist).tolist())
    return out

def _osrm_nearest_best(house_pt):
    if not check_osrm_available():
        return house_pt
        
    import requests
    import os
    base_url = os.environ.get("OSRM_BASE_URL", "http://localhost:5000")
    url = f"{base_url}/nearest/v1/driving/{house_pt[0]},{house_pt[1]}?number=10"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            d = r.json()
            if d.get("code") == "Ok":
                return d["waypoints"][0]["location"]
    except Exception as e:
        pass
    return house_pt

def _features_for_utility(utility: str) -> list:
    """
    Build GeoJSON features using a GIS Street Topology.
    1. Group customers by 'Straße'.
    2. Main Pipe: geometric route between the two farthest houses on that street.
    3. Lateral: straight line from each house to its perpendicular projection on the Main Pipe.
    """
    df = get_utility_df(utility)
    if df.empty: return []
    df = df.dropna(subset=["lat", "lon"]).copy()
    if df.empty: return []

    OFFSET = {"Gas": -0.000035, "Wasser": 0.0, "Strom": 0.000035}
    offset = OFFSET.get(utility, 0)
    DIM_MAIN, DIM_LAT = ({"Gas":"DN 150","Wasser":"DN 150","Strom":"110kV"}, {"Gas":"DN 40","Wasser":"DN 32","Strom":"400V"})
    MAT_MAIN, MAT_LAT = ({"Gas":"PE-HD","Wasser":"GG","Strom":"Kabel"}, {"Gas":"PE-HD","Wasser":"PE","Strom":"NYY-J"})

    features = []

    def project_point_to_line(pt, v, w):
        v, w, pt = np.array(v), np.array(w), np.array(pt)
        l2 = np.sum((w-v)**2)
        if l2 == 0: return v.tolist()
        t = max(0, min(1, np.dot(pt-v, w-v)/l2))
        return (v + t*(w-v)).tolist()

    if "Straße" not in df.columns:
        df["Straße"] = "Unbekannt"

    grouped = df.groupby("Straße")

    for street_name, group in grouped:
        pts = group[["lon", "lat"]].values.tolist()
        if len(pts) == 0: continue

        main_coords = []
        if len(pts) == 1:
            house_pt = pts[0]
            best_snap = _osrm_nearest_best(house_pt)
            main_coords = [best_snap, best_snap]
        else:
            # Find the two extremeties
            arr = np.array(pts)
            from scipy.spatial.distance import pdist, squareform
            dist_matrix = squareform(pdist(arr))
            i, j = np.unravel_index(np.argmax(dist_matrix, axis=None), dist_matrix.shape)
            p1, p2 = pts[i], pts[j]
            road_route = _osrm_route(p1, p2)
            if offset != 0: road_route = _offset_polyline(road_route, offset)
            main_coords = road_route

        base = {
            "utility": utility,
            "network": "Stadtnetz", # Defaulting to Stadtnetz
            "risiko": "N/A",
            "material": "N/A",
            "dimension": "N/A"
        }
        
        # Main pipe for this street
        mp = base.copy()
        mp.update({
            "type": "Main Pipe",
            "material": MAT_MAIN.get(utility, "N/A"),
            "dimension": DIM_MAIN.get(utility, "N/A"),
            "risiko": "N/A",
            "street": str(street_name)
        })
        features.append({"type":"Feature", "properties":mp, "geometry":{"type":"LineString", "coordinates":main_coords}})

        for _, row in group.iterrows():
            h_lat, h_lon = float(row["lat"]), float(row["lon"])
            house_pt = [h_lon, h_lat]
            risk = str(row.get("Risiko", "Unbekannt"))
            p_length = row.get("Länge", 0)
            try:
                p_length = float(str(p_length).replace(",", ".")) if pd.notna(p_length) else 0
            except:
                p_length = 0

            best_dist = float('inf')
            best_snap = main_coords[0] if len(main_coords) > 0 else house_pt

            if len(main_coords) >= 2:
                for idx in range(len(main_coords)-1):
                    proj = project_point_to_line(house_pt, main_coords[idx], main_coords[idx+1])
                    d = (house_pt[0]-proj[0])**2 + (house_pt[1]-proj[1])**2
                    if d < best_dist:
                        best_dist = d
                        best_snap = proj

            house_offset = offset * 0.1
            final_house_pt = [house_pt[0] + house_offset, house_pt[1] + house_offset]
            lateral_coords = [best_snap, final_house_pt]

            lat_prop = base.copy()
            lat_prop.update({
                "risiko": risk,
                "type": "Lateral",
                "material": MAT_LAT.get(utility, "n/a"),
                "dimension": DIM_LAT.get(utility, "n/a"),
                "length": f"{p_length:.1f} m" if p_length > 0 else "n/a"
            })
            features.append({"type":"Feature", "properties":lat_prop, "geometry":{"type":"LineString", "coordinates":lateral_coords}})

    return features

def regenerate_network_geojson(utilities=None) -> int:
    """
    Re-generate utility_networks.geojson from the current Excel data.
    Returns the number of GeoJSON features written.
    Only utilities with at least one valid customer row are included.
    """
    if utilities is None:
        utilities = ALL_UTILITIES
    all_features = []
    for u in utilities:
        all_features.extend(_features_for_utility(u))

    geojson = {"type": "FeatureCollection", "features": all_features}
    os.makedirs(os.path.dirname(GEOJSON_FILE), exist_ok=True)
    with open(GEOJSON_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    return len(all_features)

# ── Helper for 2_Map.py compatibility ───────────────────────────────────
def attach_geo_from_columns(df: pd.DataFrame) -> tuple:
    coords = df.apply(get_coordinates, axis=1)
    df["__lat"] = coords.apply(lambda x: x[0])
    df["__lon"] = coords.apply(lambda x: x[1])
    has_geo = df["__lat"].notna().any()
    return df, has_geo

def geocode_missing_coords(df: pd.DataFrame) -> tuple:
    # Minimal mock for compatibility
    return df, df["__lat"].notna().any()

def pick_col(df, options):
    for o in options:
        if o in df.columns: return o
    return None

def classify_priority(df):
    if "Risiko" in df.columns:
        return df["Risiko"].map({"Hoch": "critical", "Mittel": "warning", "Niedrig": "normal"}).fillna("normal")
    return pd.Series(["normal"] * len(df))

def apply_filters_case_insensitive(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    dff = df.copy()
    for col, val in filters.items():
        if col in dff.columns and val:
            dff = dff[dff[col].astype(str).str.lower() == str(val).lower()]
    return dff

def update_excel_record(customer_id: str, utility: str, field: str, new_value: str) -> bool:
    """
    Updates a specific record in the source Excel file.
    Returns True on success, False otherwise.
    """
    if not os.path.exists(EXCEL_FILE): return False
    
    try:
        df_raw = pd.read_excel(EXCEL_FILE)
        
        # 1. Find the best matching column using smart fuzzy search
        # This handles ALL columns automatically:
        #   - Shared fields (Hausnummer, Straße, Gemeinde, etc.)
        #   - Utility-specific fields (Gas Schutzrohr, Wasser Werkstoff Anschlussleitung, etc.)
        target_col = None
        field_lower = field.lower().strip()
        utility_lower = utility.lower().strip()
        
        # Pass 1: Exact match (after normalizing whitespace)
        for c in df_raw.columns:
            if c.strip().lower() == field_lower:
                target_col = c
                break
        
        # Pass 2: Utility-prefixed exact match (e.g. 'Gas Schutzrohr')
        if not target_col and utility_lower not in ['gemeinsam', '']:
            for c in df_raw.columns:
                c_norm = c.strip().lower()
                expected = f"{utility_lower} {field_lower}"
                if c_norm == expected or c_norm.endswith(field_lower) and c_norm.startswith(utility_lower):
                    target_col = c
                    break
        
        # Pass 3: Field substring match in utility-prefixed columns
        if not target_col and utility_lower not in ['gemeinsam', '']:
            for c in df_raw.columns:
                c_norm = c.strip().lower()
                if field_lower in c_norm and c_norm.startswith(utility_lower):
                    target_col = c
                    break
        
        # Pass 4: Field substring match in any column (shared fields like Hausnummer)
        if not target_col:
            for c in df_raw.columns:
                if field_lower in c.strip().lower():
                    target_col = c
                    break
        
        if not target_col:
            return False
            
        # 2. Fuzzy ID Matching
        target_sid = str(customer_id).lower().replace("kunde", "").strip()
        
        found_idx = None
        for i, val in enumerate(df_raw['Kunden']):
            v_str = str(val).lower().replace("kunde", "").strip()
            if v_str == target_sid:
                found_idx = i
                break
        
        if found_idx is None: 
            return False
        idx = found_idx
        
        # 3. Apply update
        df_raw.at[idx, target_col] = str(new_value)
        
        # 4. Save back
        try:
            # Use a context manager to ensure the file is closed
            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                df_raw.to_excel(writer, index=False)
        except Exception as e:
            df_raw.to_excel(EXCEL_FILE, index=False)
            
        invalidate_cache()
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False
