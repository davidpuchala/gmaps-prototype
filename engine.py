# engine.py — Profile synthesis, weighted scoring, OpenAI explanations

import random
import math
import json

MIN_SCORE_THRESHOLD = 75

NON_RESTAURANT_TYPES = {
    "lodging", "hotel", "motel", "spa", "gym", "health", "beauty_salon", "hair_care",
    "clothing_store", "store", "shop", "supermarket", "grocery_or_supermarket",
    "convenience_store", "gas_station", "car_wash", "parking", "school", "university",
    "library", "hospital", "doctor", "pharmacy", "dentist", "bank", "atm", "finance",
    "real_estate_agency", "travel_agency", "movie_theater", "night_club", "casino",
    "museum", "art_gallery", "tourist_attraction", "amusement_park", "zoo",
    "place_of_worship", "church", "mosque",
}

FOOD_TYPES = {
    "restaurant", "food", "bar", "cafe", "bakery", "meal_takeaway", "meal_delivery",
    "japanese_restaurant", "sushi_restaurant", "ramen_restaurant", "spanish_restaurant",
    "italian_restaurant", "french_restaurant", "chinese_restaurant", "thai_restaurant",
    "indian_restaurant", "mediterranean_restaurant", "american_restaurant",
    "mexican_restaurant", "seafood_restaurant", "steak_house", "vegetarian_restaurant",
    "vegan_restaurant", "pizza_restaurant", "fast_food_restaurant",
}

CUISINE_TO_TYPES = {
    "japanese_restaurant":      ["japanese_restaurant", "sushi_restaurant", "ramen_restaurant"],
    "sushi_restaurant":         ["sushi_restaurant", "japanese_restaurant"],
    "bar":                      ["bar", "spanish_restaurant"],
    "spanish_restaurant":       ["spanish_restaurant", "bar"],
    "italian_restaurant":       ["italian_restaurant", "pizza_restaurant"],
    "mediterranean_restaurant": ["mediterranean_restaurant", "seafood_restaurant"],
    "cafe":                     ["cafe", "bakery"],
    "fast_food_restaurant":     ["fast_food_restaurant", "meal_delivery", "meal_takeaway"],
}

USER_PROFILE = {
    "name":             "David",
    "age":              28,
    "location":         "Eixample, Barcelona",
    "reviews_count":    47,
    "avg_rating_given": 4.1,
    "visits_count":     83,
    "search_count":     34,
    "reviewed_cuisines": {
        "japanese_restaurant":      {"count": 12, "avg_rating": 4.6},
        "sushi_restaurant":         {"count": 5,  "avg_rating": 4.7},
        "bar":                      {"count": 9,  "avg_rating": 4.3},
        "spanish_restaurant":       {"count": 10, "avg_rating": 4.2},
        "italian_restaurant":       {"count": 7,  "avg_rating": 4.0},
        "mediterranean_restaurant": {"count": 5,  "avg_rating": 4.5},
        "fast_food_restaurant":     {"count": 2,  "avg_rating": 2.8},
    },
    "visited_types": {
        "japanese_restaurant":  15,
        "bar":                  18,
        "spanish_restaurant":   12,
        "italian_restaurant":   10,
        "cafe":                 8,
        "fast_food_restaurant": 3,
    },
    "saved_places": [
        "Tickets", "Bodega 1900", "Koy Shunka",
        "Compartir", "Bar Brutal", "Ramen Ya Hiro", "El Xampanyet",
    ],
    "search_history": [
        "best ramen barcelona", "japanese restaurant eixample",
        "tapas bar sant antoni", "wine bar barcelona natural wine",
        "italian restaurant barcelona", "best sushi barcelona",
        "catalan restaurant special occasion",
    ],
    "preferred_time":        "evening",
    "dining_style":          "social / dates",
    "preferred_price_level": 2,
    "disliked_types":        ["fast_food_restaurant", "meal_delivery"],
}


def synthesize_profile(user: dict) -> dict:
    raw_affinity = {}
    all_cuisines = set(list(user["reviewed_cuisines"].keys()) + list(user["visited_types"].keys()))
    for cuisine in all_cuisines:
        score        = 0.0
        review_data  = user["reviewed_cuisines"].get(cuisine, {})
        visit_count  = user["visited_types"].get(cuisine, 0)
        cuisine_word = cuisine.split("_")[0]
        save_count   = sum(1 for s in user["saved_places"] if cuisine_word in s.lower())
        save_bonus   = min(save_count * 0.1, 0.25)
        if review_data:
            quality = review_data["avg_rating"] / 5.0
            volume  = min(review_data["count"] / 15.0, 1.0)
            score  += quality * volume * 0.40
        if visit_count:
            score += min(visit_count / 20.0, 1.0) * 0.35
        score += save_bonus
        if cuisine in user.get("disliked_types", []):
            score *= 0.05
        raw_affinity[cuisine] = round(score, 4)

    top = max(raw_affinity.values()) if raw_affinity else 1.0
    cuisine_affinity = {k: round(v / top, 4) for k, v in raw_affinity.items()}

    tags = []
    if cuisine_affinity.get("japanese_restaurant", 0) > 0.7:    tags.append("Japanese fan")
    if cuisine_affinity.get("sushi_restaurant", 0) > 0.15:      tags.append("Sushi curious")
    if cuisine_affinity.get("bar", 0) > 0.7:                    tags.append("Tapas regular")
    if user["preferred_time"] == "evening":                      tags.append("Evening diner")
    if "social" in user.get("dining_style", ""):                 tags.append("Social dining")
    if user["preferred_price_level"] <= 2:                       tags.append("Mid-range")
    if user["avg_rating_given"] > 4.0:                           tags.append("Quality seeker")
    if any("natural wine" in s for s in user["search_history"]): tags.append("Natural wine")
    if any("ramen" in s for s in user["search_history"]):        tags.append("Ramen fan")

    return {
        "cuisine_affinity": cuisine_affinity,
        "price_preference": user["preferred_price_level"],
        "preferred_time":   user["preferred_time"],
        "dining_style":     user["dining_style"],
        "profile_tags":     tags,
        "disliked_types":   user.get("disliked_types", []),
        "raw_user":         user,
    }


def is_food_venue(restaurant: dict) -> bool:
    types = set(restaurant.get("types", []))
    if not types.intersection(FOOD_TYPES):
        return False
    blockers = {"lodging","hotel","motel","spa","gym","beauty_salon",
                "clothing_store","store","tourist_attraction","museum","night_club"}
    return not types.intersection(blockers)


def _cuisine_score(restaurant: dict, profile: dict) -> float:
    types = set(restaurant.get("types", []))
    best  = 0.0
    for place_type in types:
        direct = profile["cuisine_affinity"].get(place_type, 0.0)
        best = max(best, direct)
        for affinity_key, mapped in CUISINE_TO_TYPES.items():
            if place_type in mapped:
                best = max(best, profile["cuisine_affinity"].get(affinity_key, 0.0))
    return round(best * 40, 2)


def _rating_score(restaurant: dict) -> float:
    rating    = restaurant.get("rating", 0.0)
    n_reviews = restaurant.get("reviews_count", 0)
    rating_norm = max(0.0, min((rating - 4.0) / 1.0, 1.0))
    proof_boost = min(math.log10(max(n_reviews, 1)) / math.log10(5000), 1.0) * 5
    return round(rating_norm * 25 + proof_boost, 2)


def _price_score(restaurant: dict, profile: dict) -> float:
    diff = abs(restaurant.get("price_level", 2) - profile["price_preference"])
    return {0: 20.0, 1: 12.0, 2: 4.0}.get(min(diff, 3), 0.0)


def _distance_score(restaurant: dict) -> float:
    return round(max(0.0, 10 - restaurant.get("distance_km", 0.0) * 3.2), 2)


# FIX #3: Replaced fake types ('meal_sitdown', 'fast_food') with real Places API types
MODE_TYPE_FILTERS = {
    "date":   ({"restaurant", "bar", "food"},                              {"cafe", "bakery", "fast_food_restaurant", "meal_takeaway"}),
    "cafe":   ({"cafe", "bakery"},                                         {"bar", "night_club"}),
    "casual": ({"restaurant", "food"},                                     {"night_club", "fast_food_restaurant"}),
    "quick":  ({"fast_food_restaurant", "meal_takeaway", "cafe", "bakery"}, set()),
}


def score_restaurants(restaurants: list, profile: dict, exclude: set = None, mode: str = "all") -> list:
    exclude = exclude or set()
    scored  = []
    mode_req, mode_exc = MODE_TYPE_FILTERS.get(mode, (set(), set()))

    for r in restaurants:
        if r["name"] in exclude:
            continue
        if not is_food_venue(r):
            continue
        types = set(r.get("types", []))
        if types.intersection(set(profile.get("disliked_types", []))):
            continue
        if mode_req and not types.intersection(mode_req):
            continue
        if mode_exc and types.intersection(mode_exc):
            continue

        c_cuisine  = _cuisine_score(r, profile)
        c_rating   = _rating_score(r)
        c_price    = _price_score(r, profile)
        c_distance = _distance_score(r)
        raw        = c_cuisine + c_rating + c_price + c_distance

        if raw < MIN_SCORE_THRESHOLD:
            continue

        # FIX #6: Increased jitter to ±3.0 for better variety on refresh
        jitter = random.uniform(-3.0, 3.0)
        final  = round(min(raw + jitter, 99), 1)

        r_copy = r.copy()
        r_copy["score"] = final
        r_copy["score_detail"] = {
            "cuisine":  round(c_cuisine, 1),
            "rating":   round(c_rating, 1),
            "price":    round(c_price, 1),
            "distance": round(c_distance, 1),
        }
        scored.append(r_copy)

    return sorted(scored, key=lambda x: -x["score"])


def generate_explanation(restaurant: dict, profile: dict, api_key: str) -> str:
    if not api_key:
        return _template_explanation(restaurant, profile)  # FIX #2: removed stray '301' arg
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        price_map = {1: "budget", 2: "mid-range", 3: "upscale", 4: "fine dining"}
        top_3     = sorted(profile["cuisine_affinity"].items(), key=lambda x: -x[1])[:3]
        top_str   = ", ".join(
            f"{k.replace('_restaurant','').replace('_',' ')} ({int(v*100)}%)"
            for k, v in top_3
        )
        tags_str = ", ".join(profile["profile_tags"])
        user     = profile.get("raw_user", {})
        detail   = restaurant.get("score_detail", {})

        prompt = f"""You are the Google Maps 'For You' AI engine.

Write EXACTLY ONE sentence (max 18 words) explaining why {restaurant['name']}
({restaurant['cuisine']}, {restaurant['rating']}★, {price_map.get(restaurant.get('price_level',2), 'mid-range')},
{restaurant['neighborhood']}, {restaurant.get('walk_minutes',10)} min walk) matches this user.

User profile:
- Top cuisine affinities: {top_str}
- Profile tags: {tags_str}
- Prefers {user.get('preferred_time','evening')} dining, {user.get('dining_style','social')} occasions
- {user.get('reviews_count',0)} reviews written, avg rating given: {user.get('avg_rating_given',4.0)}★
- Cuisine component score: {detail.get('cuisine',0)}/40 pts

Rules:
- Reference exactly one specific signal (e.g. "your 15 Japanese visits" or "your natural wine searches")
- No filler like "you'll love it", "great choice", "perfect spot"
- Sound like a smart friend who knows your taste
- Output ONLY the sentence — no quotes, no trailing period"""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=60,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content.strip().strip('"').rstrip(".")
    except Exception as e:
        import streamlit as st
        st.warning(f"OpenAI error: {type(e).__name__}: {e}")
        return _template_explanation(restaurant, profile)


def _template_explanation(restaurant: dict, profile: dict) -> str:
    types = set(restaurant.get("types", []))
    templates = {
        "japanese_restaurant": [
            "Your 12 Japanese restaurant reviews at 4.6★ make this one of your most reliable categories",
            "Consistent with your Japanese dining pattern — 15 visits and a 4.6★ average",
        ],
        "sushi_restaurant": [
            "Your saved sushi spots and 4.7★ average signal this is squarely in your wheelhouse",
        ],
        "bar": [
            "Your 18 tapas bar visits and evening dining pattern point directly to this spot",
            "Tapas is your most-visited category — this one scores above your usual picks",
        ],
        "italian_restaurant": [
            "Italian is your fourth most-visited cuisine — this fits your quality-casual preference",
        ],
        "spanish_restaurant": [
            "Matches your authentic Spanish preference and mid-range price comfort zone",
        ],
        "mediterranean_restaurant": [
            "Your 4.5★ Mediterranean average suggests you would appreciate this one",
        ],
    }
    for t in types:
        if t in templates:
            return random.choice(templates[t])
    return (
        f"Matches your {restaurant.get('neighborhood','Barcelona')} preference "
        f"and {restaurant.get('rating',4.0)}★ quality threshold"
    )