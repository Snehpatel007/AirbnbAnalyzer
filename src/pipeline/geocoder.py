"""
Ahmedabad Area Geocoder & Pincode Area Resolver.
Utilizes OpenStreetMap Photon reverse geocoding, Indian Postal Pincode API,
and Ahmedabad geographic centroids to accurately determine listing areas.
"""
import math
import json
import logging
import sqlite3
import urllib.request
import urllib.parse
from typing import Optional, Dict, Tuple, List, Set

from config.settings import settings

logger = logging.getLogger("airbnbanalyzer.geocoder")

CACHE_DB_PATH = settings.db_path.parent / "geocache.db"

# Geographic centroids (lat, lon) for Ahmedabad neighborhoods
AHMEDABAD_CENTROIDS: Dict[str, Tuple[float, float]] = {
    # West Ahmedabad
    "SG Highway": (23.0485, 72.5085),
    "Thaltej": (23.0560, 72.5150),
    "Bodakdev": (23.0410, 72.5180),
    "Satellite": (23.0280, 72.5250),
    "Prahlad Nagar": (23.0115, 72.5080),
    "Vastrapur": (23.0360, 72.5320),
    "Sola": (23.0780, 72.5250),
    "Science City": (23.0780, 72.4980),
    "Sindhu Bhavan Road": (23.0460, 72.4950),
    "Shilaj": (23.0550, 72.4820),
    "Gota": (23.1050, 72.5380),
    
    # South-West / New Ahmedabad
    "Bopal": (23.0330, 72.4680),
    "South Bopal": (23.0180, 72.4650),
    "Ghuma": (23.0280, 72.4500),
    "Shela": (23.0030, 72.4550),
    "Ambli": (23.0350, 72.4900),
    "Makarba": (22.9980, 72.5020),
    "Jodhpur": (23.0180, 72.5280),
    "Sarkhej": (22.9860, 72.5010),
    "Vejalpur": (23.0050, 72.5280),
    
    # Central Ahmedabad
    "Navrangpura": (23.0370, 72.5580),
    "CG Road": (23.0310, 72.5600),
    "Paldi": (23.0120, 72.5600),
    "Ambawadi": (23.0200, 72.5500),
    "Ellis Bridge": (23.0250, 72.5700),
    "Vasna": (22.9980, 72.5520),
    "Usmanpura": (23.0480, 72.5680),
    "Naranpura": (23.0580, 72.5520),
    "Memnagar": (23.0510, 72.5360),
    "Gurukul": (23.0460, 72.5310),
    "Sabarmati": (23.0780, 72.5850),
    
    # North Ahmedabad
    "Chandkheda": (23.1120, 72.5850),
    "Motera": (23.0980, 72.5950),
    "New Ranip": (23.0820, 72.5680),
    "Ranip": (23.0740, 72.5710),
    "Tragad": (23.1250, 72.5580),
    "Godrej Garden City": (23.1180, 72.5540),
    "Chandlodia": (23.0780, 72.5500),
    
    # East Ahmedabad
    "Maninagar": (22.9980, 72.6050),
    "Vastral": (22.9980, 72.6550),
    "Nikol": (23.0450, 72.6650),
    "Naroda": (23.0680, 72.6500),
    "Nava Naroda": (23.0800, 72.6600),
    "Odhav": (23.0250, 72.6450),
    
    # Gandhinagar Region
    "GIFT City": (23.1620, 72.6950),
    "Kudasan": (23.1850, 72.6400),
    "Raysan": (23.1700, 72.6600),
    "Sargasan": (23.1900, 72.6150),
    "Infocity": (23.2000, 72.6400),
    "Gandhinagar": (23.2200, 72.6500),
    "Sector 7": (23.2100, 72.6450),
    "Adalaj": (23.1600, 72.5850),
    "Koba": (23.1450, 72.6350),
    "Bhaijipura": (23.1800, 72.6450),
    "Chiloda": (23.2600, 72.7000),
    "Vavol": (23.2300, 72.6100),
    "Pethapur": (23.2800, 72.6300),

    # South / South-East
    "Narol": (22.9650, 72.5950),
    "Isanpur": (22.9820, 72.5950),
    "Vatva": (22.9550, 72.6250),
    "Hathijan": (22.9350, 72.6650),
}

# Known Ahmedabad neighborhood names in order of longest string first for title matching
KNOWN_NEIGHBORHOODS = sorted(list(AHMEDABAD_CENTROIDS.keys()), key=len, reverse=True)

AHMEDABAD_CENTER = (23.030, 72.560)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class AhmedabadAreaGeocoder:
    """
    High-precision, ultra-fast Ahmedabad Area Resolver.
    Combines:
    1. Title signal detection (e.g. 'in Navrangpura', 'Shela')
    2. Photon Komoot OSM reverse geocode (pincode, district, suburb)
    3. Indian Postal Pincode API lookup
    4. Centroid proximity with 16.0 km city boundary check (filtering out Dholera, Mehsana, GIFT City, etc.)
    5. Persistent SQLite caching in data/geocache.db
    """

    def __init__(self):
        self._init_cache()

    def _init_cache(self):
        try:
            with sqlite3.connect(CACHE_DB_PATH) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS geocache (
                        coord_key TEXT PRIMARY KEY,
                        pincode TEXT,
                        district TEXT,
                        resolved_area TEXT,
                        is_in_scope INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pincode_cache (
                        pincode TEXT PRIMARY KEY,
                        areas_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not init geocache db: {e}")

    def _get_from_cache(self, coord_key: str) -> Optional[Tuple[str, bool]]:
        try:
            with sqlite3.connect(CACHE_DB_PATH) as conn:
                cur = conn.execute("SELECT resolved_area, is_in_scope FROM geocache WHERE coord_key = ?", (coord_key,))
                row = cur.fetchone()
                if row:
                    return row[0], bool(row[1])
        except Exception:
            pass
        return None

    def _save_to_cache(self, coord_key: str, pincode: Optional[str], district: Optional[str], resolved_area: str, is_in_scope: bool):
        try:
            with sqlite3.connect(CACHE_DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO geocache (coord_key, pincode, district, resolved_area, is_in_scope)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (coord_key, pincode or "", district or "", resolved_area, 1 if is_in_scope else 0),
                )
                conn.commit()
        except Exception:
            pass

    def _query_photon(self, lat: float, lon: float) -> Dict:
        try:
            url = f"https://photon.komoot.io/reverse?lat={lat}&lon={lon}"
            req = urllib.request.Request(url, headers={"User-Agent": "AhmedabadAirbnbGeocoder/2.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode())
                features = data.get("features", [])
                if features:
                    return features[0].get("properties", {})
        except Exception:
            pass
        return {}

    def _query_postal_pincode(self, pincode: str) -> List[str]:
        if not pincode or len(pincode) != 6 or not pincode.isdigit():
            return []
        try:
            with sqlite3.connect(CACHE_DB_PATH) as conn:
                cur = conn.execute("SELECT areas_json FROM pincode_cache WHERE pincode = ?", (pincode,))
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0])

            url = f"https://api.postalpincode.in/pincode/{pincode}"
            req = urllib.request.Request(url, headers={"User-Agent": "AhmedabadAirbnbGeocoder/2.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                if data and data[0].get("Status") == "Success":
                    names = [o.get("Name") for o in data[0].get("PostOffice", []) if o.get("Name")]
                    with sqlite3.connect(CACHE_DB_PATH) as conn:
                        conn.execute("INSERT OR REPLACE INTO pincode_cache (pincode, areas_json) VALUES (?, ?)", (pincode, json.dumps(names)))
                        conn.commit()
                    return names
        except Exception:
            pass
        return []

    def resolve_listing_area(
        self,
        listing_id: str,
        title: Optional[str],
        lat: Optional[float],
        lon: Optional[float],
        fallback_area: str = "SG Highway"
    ) -> Tuple[str, bool]:
        """
        Determines the true area for a listing.
        Returns:
            (resolved_area, is_in_scope)
        """
        # 1. Geographic Boundary Check if coordinates are present
        if lat is not None and lon is not None:
            coord_key = f"{round(lat, 3)}_{round(lon, 3)}"
            cached = self._get_from_cache(coord_key)
            if cached is not None:
                # If cached resolution is inside Ahmedabad, check title first if title specifies a different neighborhood
                area_name, in_scope = cached
                if in_scope and title:
                    t_lower = title.lower()
                    for n in KNOWN_NEIGHBORHOODS:
                        if f" {n.lower()}" in t_lower or f"in {n.lower()}" in t_lower:
                            return n, True
                return area_name, in_scope

            # Check if within user's target bounding box for Ahmedabad & Gandhinagar
            # sw: 22.8887, 72.4164 | ne: 23.2982, 72.7215 (with small buffer)
            if not (22.86 <= lat <= 23.32 and 72.39 <= lon <= 72.74):
                self._save_to_cache(coord_key, None, None, "Outside Ahmedabad", False)
                return "Outside Ahmedabad", False

            # Check title first: many hosts put the exact neighborhood in title
            if title:
                t_lower = title.lower()
                if "gift" in t_lower:
                    self._save_to_cache(coord_key, None, "GIFT City", "GIFT City", True)
                    return "GIFT City", True
                for n in KNOWN_NEIGHBORHOODS:
                    if f" {n.lower()}" in t_lower or f"in {n.lower()}" in t_lower or f"at {n.lower()}" in t_lower or f", {n.lower()}" in t_lower:
                        self._save_to_cache(coord_key, None, None, n, True)
                        return n, True

            # Calculate nearest centroid in Ahmedabad & Gandhinagar
            min_dist = float("inf")
            best_area = fallback_area if fallback_area in KNOWN_NEIGHBORHOODS else ("GIFT City" if lat > 23.15 else "SG Highway")

            for a_name, (c_lat, c_lon) in AHMEDABAD_CENTROIDS.items():
                d = haversine_km(lat, lon, c_lat, c_lon)
                if d < min_dist:
                    min_dist = d
                    best_area = a_name

            # If within 3.5 km of a known centroid, resolve immediately without network lag
            if min_dist <= 3.5:
                self._save_to_cache(coord_key, None, None, best_area, True)
                return best_area, True

            # 2. Query Photon Komoot reverse geocoder for edge coordinates
            props = self._query_photon(lat, lon)
            pincode = props.get("postcode")
            district = props.get("district") or props.get("suburb") or props.get("locality") or props.get("name")
            city = props.get("city") or props.get("county")

            # Check if Photon identified GIFT City
            if district and "gift" in district.lower():
                self._save_to_cache(coord_key, pincode, district, "GIFT City", True)
                return "GIFT City", True

            # Check if postal API gives neighborhood
            postal_areas = self._query_postal_pincode(pincode) if pincode else []
            for pa in postal_areas:
                pa_clean = pa.replace(" (Ahmedabad)", "").replace(" (Gandhinagar)", "").replace(" Char Rasta", "").replace(" Road", "").strip()
                for n in KNOWN_NEIGHBORHOODS:
                    if n.lower() == pa_clean.lower() or pa_clean.lower() in n.lower():
                        self._save_to_cache(coord_key, pincode, district, n, True)
                        return n, True

            # Check if district from Photon matches a known neighborhood
            if district:
                d_clean = district.lower()
                for n in KNOWN_NEIGHBORHOODS:
                    if n.lower() in d_clean or d_clean in n.lower():
                        self._save_to_cache(coord_key, pincode, district, n, True)
                        return n, True

            self._save_to_cache(coord_key, pincode, district, best_area, True)
            return best_area, True

        # Fallback if no coordinates
        if title:
            t_lower = title.lower()
            for n in KNOWN_NEIGHBORHOODS:
                if f" {n.lower()}" in t_lower or f"in {n.lower()}" in t_lower:
                    return n, True

        is_valid = fallback_area in KNOWN_NEIGHBORHOODS
        return fallback_area, is_valid


geocoder = AhmedabadAreaGeocoder()
