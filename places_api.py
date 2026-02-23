# places_api.py — All Google Places API interactions
# Search anchor: Plaça de Catalunya (41.3870, 2.1700)

import requests
import streamlit as st

PLACES_BASE  = "https://maps.googleapis.com/maps/api/place"
GEOCODE_BASE = "https://maps.googleapis.com/maps/api/geocode"

# Plaça de Catalunya — single source of truth for all location references
CENTER_LAT = 41.3870
CENTER_LNG = 2.1700

DETAIL_FIELDS = (
    "name,rating,user_ratings_total,price_level,"
    "vicinity,geometry,opening_hours,photos,types,"
    "formatted_address,url"
)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_nearby_restaurants(api_key: str, radius: int = 1500, min_rating: float = 4.0) -> list:
    """
    FIX #4: radius is now a parameter so the UI slider actually affects results.
    Calls Places Nearby Search around Plaça de Catalunya.
    Returns up to 60 results (3 pages x 20), filtered by min_rating.
    """
    results = []
    url     = f"{PLACES_BASE}/nearbysearch/json"
    params  = {
        "location": f"{CENTER_LAT},{CENTER_LNG}",
        "radius":   radius,
        "type":     "restaurant",
        "key":      api_key,
    }
    for _page in range(3):
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            break
        for place in data.get("results", []):
            if place.get("rating", 0) >= min_rating:
                results.append(place)
        next_token = data.get("next_page_token")
        if not next_token:
            break
        import time; time.sleep(2)
        params = {"pagetoken": next_token, "key": api_key}
    return results


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_place_details(place_id: str, api_key: str) -> dict:
    url    = f"{PLACES_BASE}/details/json"
    params = {"place_id": place_id, "fields": DETAIL_FIELDS, "key": api_key}
    resp   = requests.get(url, params=params, timeout=10)
    return resp.json().get("result", {})


def build_photo_url(photo_reference: str, api_key: str, max_width: int = 800) -> str:
    return (
        f"{PLACES_BASE}/photo"
        f"?maxwidth={max_width}"
        f"&photo_reference={photo_reference}"
        f"&key={api_key}"
    )


def get_opening_status(details: dict) -> tuple[str, str]:
    oh       = details.get("opening_hours", {})
    open_now = oh.get("open_now")
    periods  = oh.get("periods", [])
    if open_now is None:
        return "unknown", "Hours unavailable"
    if not open_now:
        return "closed", "Closed now"
    from datetime import datetime
    now       = datetime.now()
    g_weekday = (now.weekday() + 1) % 7
    for period in periods:
        close = period.get("close", {})
        if close.get("day") == g_weekday:
            close_time    = close.get("time", "2359")
            close_h, close_m = int(close_time[:2]), int(close_time[2:])
            mins_to_close = (close_h * 60 + close_m) - (now.hour * 60 + now.minute)
            if 0 < mins_to_close <= 60:
                return "closing_soon", f"Closes soon · {close_h}:{close_time[2:]}"
            elif mins_to_close > 0:
                return "open", f"Open · Closes {close_h}:{close_time[2:]}"
    return "open", "Open now"


def classify_cuisine(types: list, name: str) -> str:
    cuisine_map = {
        "japanese_restaurant":      "Japanese",
        "sushi_restaurant":         "Japanese · Sushi",
        "ramen_restaurant":         "Japanese · Ramen",
        "chinese_restaurant":       "Chinese",
        "thai_restaurant":          "Thai",
        "indian_restaurant":        "Indian",
        "italian_restaurant":       "Italian",
        "pizza_restaurant":         "Italian · Pizza",
        "spanish_restaurant":       "Spanish",
        "mediterranean_restaurant": "Mediterranean",
        "french_restaurant":        "French",
        "american_restaurant":      "American",
        "mexican_restaurant":       "Mexican",
        "seafood_restaurant":       "Seafood",
        "steak_house":              "Steakhouse",
        "vegetarian_restaurant":    "Vegetarian",
        "vegan_restaurant":         "Vegan",
        "cafe":                     "Café",
        "bakery":                   "Bakery",
        "bar":                      "Bar · Tapas",
        "fast_food_restaurant":     "Fast Food",
    }
    for t in types:
        if t in cuisine_map:
            return cuisine_map[t]
    name_lower = name.lower()
    if any(w in name_lower for w in ["ramen","sushi","japanese","nippon","tokyo"]): return "Japanese"
    if any(w in name_lower for w in ["tapas","bodega","bar","tasca","taverna"]):    return "Spanish · Tapas"
    if any(w in name_lower for w in ["pizza","pasta","trattoria","osteria"]):       return "Italian"
    if any(w in name_lower for w in ["thai","bangkok"]):                            return "Thai"
    if any(w in name_lower for w in ["cafe","café","coffee"]):                      return "Café"
    return "Restaurant"


def get_neighborhood(vicinity: str) -> str:
    if not vicinity:
        return "Barcelona"
    parts = vicinity.split(",")
    return parts[-2].strip() if len(parts) >= 2 else parts[0].strip()


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    import math
    R    = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a    = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlng/2)**2
    return round(R * 2 * math.asin(math.sqrt(a)), 2)


def enrich_restaurant(place: dict, api_key: str) -> dict | None:
    place_id = place.get("place_id")
    if not place_id:
        return None
    details  = fetch_place_details(place_id, api_key)
    name     = details.get("name") or place.get("name", "Unknown")
    types    = details.get("types") or place.get("types", [])
    vicinity = details.get("vicinity") or place.get("vicinity", "")
    geometry = details.get("geometry") or place.get("geometry", {})
    location = geometry.get("location", {})
    lat      = location.get("lat", CENTER_LAT)
    lng      = location.get("lng", CENTER_LNG)
    photos   = details.get("photos") or place.get("photos", [])
    if not photos:
        return None
    photo_ref = photos[0].get("photo_reference", "")
    photo_url = build_photo_url(photo_ref, api_key) if photo_ref else None
    if not photo_url:
        return None
    distance_km  = haversine_km(CENTER_LAT, CENTER_LNG, lat, lng)
    walk_minutes = max(1, round(distance_km / 0.08))
    status_key, status_text = get_opening_status(details)
    rating        = details.get("rating") or place.get("rating", 0)
    reviews_count = details.get("user_ratings_total") or place.get("user_ratings_total", 0)
    price_level   = details.get("price_level") or place.get("price_level", 2)
    return {
        "name":           name,
        "place_id":       place_id,
        "cuisine":        classify_cuisine(types, name),
        "neighborhood":   get_neighborhood(vicinity),
        "rating":         rating,
        "reviews_count":  reviews_count,
        "price_level":    price_level if price_level else 2,
        "distance_km":    distance_km,
        "walk_minutes":   walk_minutes,
        "types":          types,
        "opening_status": status_key,
        "opening_hours":  status_text,
        "photo_url":      photo_url,
        "maps_url":       details.get("url", ""),
        "lat":            lat,
        "lng":            lng,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def load_all_restaurants(api_key: str, radius: int = 1500) -> list:
    """FIX #4: radius passed through so the UI slider actually affects search area."""
    raw      = fetch_nearby_restaurants(api_key, radius=radius)
    enriched = []
    for place in raw:
        r = enrich_restaurant(place, api_key)
        if r and r["rating"] >= 4.0 and r["reviews_count"] >= 50:
            enriched.append(r)
    return enriched