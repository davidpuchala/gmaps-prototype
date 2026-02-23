# 🗺️ For You — Google Maps Personalized Restaurant Recommendations

A Streamlit prototype of an AI-powered "For You" feature for Google Maps — 
a personalized restaurant recommendation engine embedded as a mobile bottom sheet,
replacing the generic "Local Vibe" / "Trending" tab with picks tailored to you.

## Demo

The app simulates the Google Maps mobile experience:
- **Map background**: Live interactive Google Maps iframe with pinned restaurants
- **Bottom sheet**: Three states — collapsed, half-open (teaser), full-open (all 3 cards)
- **Restaurant cards**: Real photos, walking distance, opening status, match score, and a one-sentence Claude-generated "why you'll like this" explanation
- **Feedback loop**: Intent buttons (👍/😐/👎) + post-visit star rating → feeds back into engine accuracy

## Architecture

```
Google Places Nearby Search (Pl. Catalunya, 2.5km radius)
        ↓
Place Details API (photos, opening hours, types, URL)
        ↓
Enrichment pipeline (cuisine classification, distance, walk time, status)
        ↓
Profile Synthesis (reviews 40% · visits 35% · saves 25%)
        ↓
Weighted Scoring (cuisine match 40% · rating 30% · price 20% · distance 10%)
        ↓
Top 3 Recommendations
        ↓
Claude API → one-sentence personalized explanation per restaurant
        ↓
Google Maps iframe (bottom sheet UI) + Two-stage feedback loop
```

## Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/for-you-maps
cd for-you-maps
pip install -r requirements.txt
```

### 2. Add your API keys

Copy the secrets template:
```bash
cp secrets.toml.template .streamlit/secrets.toml
```

Then edit `.streamlit/secrets.toml`:
```toml
GOOGLE_PLACES_API_KEY = "your_real_key_here"
ANTHROPIC_API_KEY     = "your_real_key_here"
```

> ⚠️ `.streamlit/secrets.toml` is gitignored. Never commit it.

### 3. Enable APIs in Google Cloud Console

Go to [console.cloud.google.com](https://console.cloud.google.com) and enable:
- **Places API** (Nearby Search + Place Details + Photos)
- **Maps Embed API** (for the interactive map iframe)

### 4. Run

```bash
streamlit run app.py
```

## File Structure

```
├── app.py                  # Streamlit UI — bottom sheet, all states
├── places_api.py           # Google Places API — fetch, enrich, cache
├── engine.py               # Recommendation logic — synthesis, scoring, Claude explanations
├── requirements.txt
├── secrets.toml.template   # Safe to commit — template only
├── .streamlit/
│   └── secrets.toml        # GITIGNORED — your real keys go here
├── .gitignore
└── README.md
```

## Key Design Decisions

**Why a weighted scoring function, not ML?**  
Collaborative filtering requires a user-restaurant rating matrix that isn't available via the Places API. The weighted function is interpretable, fast, and sufficient to demonstrate the recommendation concept — it's explicitly framed as a proxy for production ML in the pipeline documentation.

**Why Claude for explanations?**  
The one-sentence "why you'll like this" is the core AI value of the feature. A scoring function can rank — only a language model can articulate *why* a place fits your taste profile in a way that feels personal rather than algorithmic.

**Why Streamlit secrets, not hardcoded keys?**  
Google Places API keys are billable. Exposing them in a public GitHub repo risks unauthorized usage and charges.

**Why cache API calls?**  
`@st.cache_data(ttl=3600)` means the Places API is called once per hour maximum, not on every Streamlit rerun. This keeps costs near zero during development and demo recording.

## Assignment Context

Individual Assignment 1 — Prototyping Products with Data and AI  
ESADE MSc Business Analytics, 2026  
Course: Prototyping Products with Data & AI (Prof. José A. Rodríguez-Serrano)
