import json
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import time

st.set_page_config(
    page_title="Google Maps · For You",
    page_icon="🗺️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

try:
    GPLACES_KEY = st.secrets["GOOGLE_PLACES_API_KEY"]
    OPENAI_KEY  = st.secrets["OPENAI_API_KEY"]
except Exception:
    GPLACES_KEY = ""
    OPENAI_KEY  = ""

if not GPLACES_KEY:
    st.error("⚠️ No GOOGLE_PLACES_API_KEY in .streamlit/secrets.toml")
    st.stop()

from places_api import load_all_restaurants, CENTER_LAT, CENTER_LNG
from engine import synthesize_profile, score_restaurants, generate_explanation, USER_PROFILE

# ── CSS: hide all Streamlit chrome, full-viewport layout ─────────────────────
# FIX #7: overflow:hidden on html/body + full height forces true fullscreen
st.markdown("""
<style>
#MainMenu, footer, header, .stAppDeployButton,
.stStatusWidget, .stDecoration { visibility: hidden !important; display: none !important }
html, body, .stApp {
    background: #1a1a2e !important;
    margin: 0 !important; padding: 0 !important;
    overflow: hidden !important;
    height: 100% !important;
    width: 100% !important;
}
.block-container {
    padding: 0 !important;
    max-width: 393px !important;
    margin: 0 auto !important;
    background: transparent !important;
    height: 100% !important;
}
section[data-testid="stMain"] {
    background: #1a1a2e !important;
    overflow: hidden !important;
    padding: 0 !important;
    height: 100% !important;
}
section[data-testid="stMain"] > div { background: transparent !important; height: 100% !important }
div[data-testid="stVerticalBlock"] { gap: 0 !important; background: transparent !important; height: 100% !important }
div[data-testid="stVerticalBlockSeparator"] { display: none !important }
div[data-testid="stMainBlockContainer"] { padding: 0 !important; margin: 0 auto !important; height: 100% !important }
div[data-testid="element-container"] { padding: 0 !important; margin: 0 !important; }
div[data-testid="stCustomComponentV1"] {
    background: transparent !important; border: none !important;
    padding: 0 !important; margin: 0 !important; box-shadow: none !important;
    height: 100% !important;
}
div[data-testid="stCustomComponentV1"] iframe {
    background: transparent !important; border: none !important; display: block !important;
    height: 100% !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [("recs", []), ("profile", None), ("excluded", set()),
             ("radius", 1500), ("mode", "all"), ("refresh", False)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Load / refresh recommendations ───────────────────────────────────────────
if not st.session_state.recs or st.session_state.refresh:
    st.session_state.refresh = False
    with st.spinner("Finding your picks…"):
        # FIX #4: pass radius so slider affects actual search area
        restaurants = load_all_restaurants(GPLACES_KEY, radius=st.session_state.radius)
        if not restaurants:
            st.error("No restaurants returned — check API key / quota.")
            st.stop()
        profile = synthesize_profile(USER_PROFILE)
        scored  = score_restaurants(
            restaurants, profile,
            exclude=st.session_state.excluded,
            mode=st.session_state.mode,
        )
        if not scored:
            scored = score_restaurants(restaurants, profile, exclude=st.session_state.excluded, mode="all")
        top3 = scored[:3]
        for r in top3:
            r["explanation"] = generate_explanation(r, profile, OPENAI_KEY)
            time.sleep(1)
        st.session_state.recs    = top3
        st.session_state.profile = profile
        st.session_state.excluded |= {r["name"] for r in top3}

recs    = st.session_state.recs
profile = st.session_state.profile

if recs and profile is None:
    profile = synthesize_profile(USER_PROFILE)
    st.session_state.profile = profile

# ── Serialise for JS ──────────────────────────────────────────────────────────
def r_to_js(r):
    sd = r.get("score_detail", {"cuisine": 0, "rating": 0, "price": 0, "distance": 0})
    maps_url = (r.get("maps_url") or
                f'https://www.google.com/maps/search/{r["name"].replace(" ","+")},+Barcelona')
    return {
        "name": r["name"], "cuisine": r["cuisine"],
        "neighborhood": r["neighborhood"], "rating": r["rating"],
        "reviews": r["reviews_count"], "price": r.get("price_level", 2),
        "distance": r["distance_km"], "walk": r["walk_minutes"],
        "status": r["opening_status"], "hours": r["opening_hours"],
        "photo": r["photo_url"], "maps_url": maps_url,
        "score": int(r["score"]), "explanation": r.get("explanation", ""),
        "detail": sd,
        "lat": r.get("lat", CENTER_LAT), "lng": r.get("lng", CENTER_LNG),
    }

tags_js  = json.dumps(profile.get("profile_tags", []))
recs_js  = json.dumps([r_to_js(r) for r in recs])
af       = profile.get("cuisine_affinity", {})
top_af   = sorted(af.items(), key=lambda x: -x[1])[:6]
af_js    = json.dumps([{
    "name": k.replace("_restaurant","").replace("_"," ").title(),
    "pct":  int(v * 100),
} for k, v in top_af])
now_str  = datetime.now().strftime("%H:%M")
map_key  = GPLACES_KEY

# Build nav URLs and mode/radius state to pass into the HTML
cur_mode   = st.session_state.mode
radius_m   = st.session_state.radius

# ── Full-viewport HTML: map + controls + bottom sheet ─────────────────────────
# FIX #7: iframe height=900 + 100dvh inside ensures true fullscreen on iPhone
# FIX #1: All location refs changed to Pl. Catalunya
# FIX #8: Removed stray semicolon in !isHalf ternary
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
:root{{
  --blue:#1a73e8;--blue-l:#e8f0fe;--blue-d:#1557b0;
  --green:#188038;--orange:#e37400;--red:#d93025;
  --g1:#202124;--g2:#3c4043;--g3:#5f6368;--g4:#80868b;
  --g5:#dadce0;--g6:#f1f3f4;--g7:#f8f9fa;
  --sh1:0 1px 3px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.08);
  --sh2:0 4px 16px rgba(0,0,0,.18);
  --sh3:0 -2px 20px rgba(0,0,0,.15);
  --r:16px;--tab-h:56px;--sheet-r:20px;
}}
/* FIX #7: 100dvh covers full iPhone screen including safe areas */
html,body{{
  width:100%;height:100dvh;overflow:hidden;
  font-family:'Roboto',sans-serif;background:transparent;color:var(--g1);
}}
#map{{position:fixed;inset:0;width:100%;height:100%;background:#e8eaed}}

/* Top bar — 64px clears the iPhone wrapper's 59px status bar + Dynamic Island */
#topbar{{position:fixed;top:64px;left:0;right:0;padding:0 12px;z-index:40;pointer-events:none;display:flex;flex-direction:column;gap:6px}}
.search-pill{{background:#fff;border-radius:28px;box-shadow:var(--sh2);display:flex;align-items:center;height:38px;padding:0 10px;gap:8px;pointer-events:all}}
.pill-text{{flex:1;font-size:13px;color:var(--g3)}}
.pill-avatar{{width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,#1a73e8,#34a853);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0}}

/* Control chip strip below search pill */
.chip-ctrl-row{{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;pointer-events:all;padding-bottom:2px}}
.chip-ctrl-row::-webkit-scrollbar{{display:none}}
/* Mode / radius / refresh chips — pure display, JS onclick triggers Python via query_params */
button.ctrl-chip{{
  display:inline-flex;align-items:center;gap:4px;
  background:rgba(255,255,255,.93);border:1px solid rgba(218,220,224,.8);
  border-radius:18px;padding:5px 12px;font-size:12px;font-weight:500;
  color:var(--g2);white-space:nowrap;flex-shrink:0;cursor:pointer;
  box-shadow:0 1px 3px rgba(0,0,0,.2);backdrop-filter:blur(4px);
  font-family:'Roboto',sans-serif;
}}
button.ctrl-chip:hover{{background:rgba(241,243,244,.97)}}
button.ctrl-chip.active{{background:rgba(232,240,254,.97);border-color:var(--blue);color:var(--blue)}}
button.ctrl-chip.refresh{{border-color:rgba(26,115,232,.5);color:var(--blue)}}

/* Radius label chip (non-clickable display) */
span.radius-lbl{{
  display:inline-flex;align-items:center;
  background:rgba(255,255,255,.93);border:1px solid rgba(218,220,224,.8);
  border-radius:18px;padding:5px 10px;font-size:12px;font-weight:500;
  color:var(--g3);white-space:nowrap;flex-shrink:0;
  box-shadow:0 1px 3px rgba(0,0,0,.2);backdrop-filter:blur(4px);
}}

/* Bottom sheet */
#sheet{{position:fixed;bottom:0;left:0;right:0;background:#fff;border-radius:var(--sheet-r) var(--sheet-r) 0 0;box-shadow:var(--sh3);z-index:30;display:flex;flex-direction:column}}
.handle-wrap{{padding:8px 0 2px;flex-shrink:0;cursor:grab;touch-action:none}}
.handle{{width:36px;height:4px;border-radius:2px;background:var(--g5);margin:0 auto}}
#sheet-content{{flex:1;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;touch-action:pan-y;padding-bottom:calc(var(--tab-h)+72px)}}
#sheet-content::-webkit-scrollbar{{width:3px}}
#sheet-content::-webkit-scrollbar-thumb{{background:var(--g5);border-radius:2px}}
#sheet-footer{{flex-shrink:0;background:#fff}}
.sh-header{{display:flex;align-items:center;justify-content:space-between;padding:8px 18px 0}}
.sh-title{{font-size:15px;font-weight:500;color:var(--g1);display:flex;align-items:center;gap:8px}}
.badge{{background:var(--blue-l);color:var(--blue);font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;letter-spacing:.3px}}
.sh-sub{{font-size:12px;color:var(--g3)}}
.chip-strip{{display:flex;gap:6px;overflow-x:auto;padding:4px 18px 2px;scrollbar-width:none}}
.chip-strip::-webkit-scrollbar{{display:none}}
.chip{{background:var(--blue-l);border:1px solid var(--blue);color:var(--blue);border-radius:18px;padding:4px 11px;font-size:12px;font-weight:500;white-space:nowrap;flex-shrink:0}}
.slabel{{font-size:10px;font-weight:600;letter-spacing:.9px;text-transform:uppercase;color:var(--g3);padding:10px 18px 6px}}
.rcard{{margin:0 14px 12px;border-radius:var(--r);border:1px solid var(--g5);overflow:hidden;box-shadow:var(--sh1);background:#fff}}
.rcard-img{{width:100%;height:160px;object-fit:cover;display:block}}
.rcard-body{{padding:12px 14px 6px}}
.rcard-rank{{font-size:10px;font-weight:600;letter-spacing:.9px;text-transform:uppercase;color:var(--blue);margin-bottom:3px}}
.rcard-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px}}
.rcard-name{{font-size:16px;font-weight:500;color:var(--g1);line-height:1.2;flex:1;margin-right:8px}}
.match-badge{{background:var(--blue);color:#fff;font-size:11px;font-weight:700;padding:3px 9px;border-radius:10px;flex-shrink:0}}
.rcard-cuisine{{font-size:13px;color:var(--g3);margin-bottom:8px}}
.meta-row{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}}
.meta-item{{display:flex;align-items:center;gap:3px;font-size:12px;color:var(--g3)}}
.stars{{color:#fbbc04;font-size:12px;letter-spacing:1px}}
.status-open{{color:var(--green);font-weight:500;font-size:12px}}
.status-closing{{color:var(--orange);font-weight:500;font-size:12px}}
.status-closed{{color:var(--red);font-weight:500;font-size:12px}}
.why{{background:var(--blue-l);border-radius:10px;padding:8px 11px;margin-bottom:10px;font-size:12px;color:#1a3464;line-height:1.5;display:flex;gap:6px;align-items:flex-start}}
.rcard-actions{{display:flex;gap:8px;padding:0 14px 12px}}
.btn-dir{{flex:1;background:var(--blue);color:#fff;border:none;border-radius:18px;padding:8px 0;font-size:13px;font-weight:500;cursor:pointer;font-family:'Roboto',sans-serif;text-align:center;text-decoration:none;display:inline-block}}
.btn-save{{background:var(--g6);color:var(--g2);border:1px solid var(--g5);border-radius:18px;padding:8px 14px;font-size:13px;font-weight:500;cursor:pointer;font-family:'Roboto',sans-serif}}
.btn-save.saved{{background:var(--blue-l);color:var(--blue);border-color:var(--blue)}}
.fb-row{{display:flex;gap:6px;padding:0 14px 10px}}
.fb-btn{{flex:1;border:1px solid var(--g5);border-radius:18px;padding:7px 0;font-size:12px;font-weight:500;background:var(--g7);color:var(--g2);cursor:pointer;font-family:'Roboto',sans-serif;text-align:center;transition:all .15s}}
.fb-btn:hover{{background:var(--g6)}}
.score-detail{{margin:0 14px 10px;background:var(--g7);border-radius:10px;padding:10px 12px}}
.score-row{{display:flex;justify-content:space-between;margin-bottom:5px;font-size:11px;color:var(--g3)}}
.score-bar-track{{background:var(--g5);border-radius:3px;height:4px;overflow:hidden;margin-top:3px}}
.score-bar-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--blue),#34a853)}}
.divider{{height:1px;background:var(--g6);margin:4px 18px}}
.hist-row{{padding:10px 18px;border-bottom:1px solid var(--g6)}}
.hist-row:last-child{{border-bottom:none}}
.hist-name{{font-size:14px;font-weight:500;color:var(--g1);margin-bottom:2px}}
.hist-meta{{font-size:12px;color:var(--g3);margin-bottom:6px}}
.hist-badges{{display:flex;gap:5px;flex-wrap:wrap}}
.hist-badge{{font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid var(--g5);background:var(--g7);color:var(--g2)}}
.hist-badge.intent{{background:var(--blue-l);border-color:var(--blue);color:var(--blue)}}
.hist-badge.svd{{background:#e6f4ea;border-color:#188038;color:#188038}}
.aff-row{{padding:4px 18px 6px}}
.aff-label{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px}}
.aff-track{{background:var(--g5);border-radius:3px;height:5px;overflow:hidden}}
.aff-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--blue),#34a853)}}
.metrics{{display:flex;padding:8px 18px}}
.metric{{flex:1;text-align:center;border-right:1px solid var(--g5)}}
.metric:last-child{{border-right:none}}
.metric-val{{font-size:20px;font-weight:700;color:var(--g1)}}
.metric-lbl{{font-size:11px;color:var(--g3);margin-top:2px}}
.pipe-row{{display:flex;gap:10px;align-items:flex-start;padding:10px 18px;border-bottom:1px solid var(--g6)}}
.pipe-row:last-child{{border-bottom:none}}
.pipe-icon{{font-size:16px;width:22px;flex-shrink:0;margin-top:1px}}
.pipe-lbl{{font-size:13px;font-weight:500;color:var(--g1)}}
.pipe-val{{font-size:11px;color:var(--g3);margin-top:1px}}
.empty{{padding:32px 18px;text-align:center;color:var(--g3);font-size:14px}}
.back-btn{{display:flex;align-items:center;gap:4px;padding:12px 18px 8px;font-size:14px;font-weight:500;color:var(--blue);cursor:pointer}}
.swipe-hint{{text-align:center;font-size:11px;color:var(--g4);padding:6px 0 8px;cursor:pointer}}
#tabs{{position:fixed;bottom:0;left:0;right:0;height:var(--tab-h);background:#fff;border-top:1px solid var(--g5);display:flex;z-index:50;padding-bottom:env(safe-area-inset-bottom)}}
.tab{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;cursor:pointer;color:var(--g3);font-size:10px;font-weight:500;padding:6px 0;user-select:none;transition:color .15s}}
.tab.active{{color:var(--blue)}}
.tab-icon{{font-size:22px;line-height:1}}
</style>
</head>
<body>
<div id="map"></div>

<div id="topbar">
  <div class="search-pill">
    <svg width="18" height="22" viewBox="0 0 100 130" style="flex-shrink:0" xmlns="http://www.w3.org/2000/svg">
      <path d="M50,4 C32,4 17,15 10,30 L50,50 Z" fill="#F15B43"/>
      <path d="M50,4 C68,4 83,15 90,30 L50,50 Z" fill="#519AF6"/>
      <path d="M10,30 C6,38 4,44 4,50 C4,68 14,84 28,97 L50,50 Z" fill="#FBC608"/>
      <path d="M90,30 C94,38 96,44 96,50 C96,68 86,84 72,97 L50,126 L28,97 L50,50 Z" fill="#3AB366"/>
      <circle cx="50" cy="46" r="22" fill="white"/>
    </svg>
    <span class="pill-text">Search here</span>
    <div class="pill-avatar">D</div>
  </div>
</div>

<div id="sheet">
  <div class="handle-wrap" id="handle-wrap"><div class="handle"></div></div>
  <div id="sheet-content"></div>
  <div id="sheet-footer"></div>
</div>

<div id="tabs">
  <div class="tab active" id="tab-explore" onclick="setTab('explore')">
    <span class="tab-icon">🔍</span><span>Explore</span>
  </div>
  <div class="tab" id="tab-you" onclick="setTab('you')">
    <span class="tab-icon">👤</span><span>You</span>
  </div>
  <div class="tab" id="tab-contribute" onclick="setTab('contribute')">
    <span class="tab-icon">✏️</span><span>Contribute</span>
  </div>
</div>

<script>
const RECS    = {recs_js};
const TAGS    = {tags_js};
const AF      = {af_js};
const NOW     = "{now_str}";
const MAP_KEY = "{map_key}";
const CENTER  = {{ lat:{CENTER_LAT}, lng:{CENTER_LNG} }};

// Control state — managed purely in JS, no Python rerun for display changes
// Mode/radius changes that need new data post a message to the parent Streamlit page
const MODES = [
  {{id:'all',   label:'All'}},
  {{id:'date',  label:'🕯 Date'}},
  {{id:'cafe',  label:'☕ Café'}},
  {{id:'casual',label:'🍽 Casual'}},
  {{id:'quick', label:'⚡ Quick'}},
];
const RADII = [500, 1000, 1500, 2000];
let curMode   = '{cur_mode}';
let curRadius = {radius_m};

// Build control chips
function buildChips() {{
  const row = document.getElementById('ctrl-chips');
  row.innerHTML = '';
  MODES.forEach(m => {{
    const btn = document.createElement('button');
    btn.className = 'ctrl-chip' + (m.id === curMode ? ' active' : '');
    btn.textContent = m.label;
    btn.onclick = () => triggerReload('mode', m.id);
    row.appendChild(btn);
  }});
  // Radius label (display only)
  const lbl = document.createElement('span');
  lbl.className = 'radius-lbl';
  lbl.textContent = curRadius >= 1000 ? (curRadius/1000).toFixed(1)+'km' : curRadius+'m';
  row.appendChild(lbl);
  // Radius decrease / increase
  [[-500,'−'],[ 500,'+']].forEach(([delta, sym]) => {{
    const btn = document.createElement('button');
    btn.className = 'ctrl-chip';
    btn.textContent = sym;
    btn.onclick = () => {{
      const next = Math.max(500, Math.min(2000, curRadius + delta));
      if (next !== curRadius) triggerReload('radius', next);
    }};
    row.appendChild(btn);
  }});
  // Refresh chip
  const ref = document.createElement('button');
  ref.className = 'ctrl-chip refresh';
  ref.textContent = '🔄 New';
  ref.onclick = () => triggerReload('refresh');
  row.appendChild(ref);
}}

// Trigger a Streamlit rerun by navigating the parent window with query params
function triggerReload(action, value) {{
  const base = window.top.location.href.split('?')[0];
  let qs = 'action=' + action;
  if (value !== undefined) qs += '&value=' + value;
  window.top.location.href = base + '?' + qs;
}}

// ── MAP ───────────────────────────────────────────────────────────────────────
let gmap = null, mapMarkers = [];

function initMap() {{
  gmap = new google.maps.Map(document.getElementById('map'), {{
    center: CENTER, zoom: 15,
    disableDefaultUI: true, gestureHandling: 'greedy',
    styles: [
      {{featureType:'poi',elementType:'labels',stylers:[{{visibility:'off'}}]}},
      {{featureType:'transit.station',elementType:'labels',stylers:[{{visibility:'off'}}]}},
    ],
  }});
  // Blue accuracy circle — Pl. Catalunya
  new google.maps.Circle({{
    map:gmap, center:CENTER, radius:40,
    fillColor:'#4185F4', fillOpacity:.15,
    strokeColor:'#4185F4', strokeOpacity:.4, strokeWeight:1, zIndex:1,
  }});
  // FIX #1: marker title updated to Plaça de Catalunya
  new google.maps.Marker({{
    position:CENTER, map:gmap, zIndex:2, title:'Plaça de Catalunya',
    icon:{{ path:google.maps.SymbolPath.CIRCLE, scale:9,
      fillColor:'#4185F4', fillOpacity:1, strokeColor:'#fff', strokeWeight:2.5 }},
  }});
  placeMarkers();
}}

function placeMarkers() {{
  mapMarkers.forEach(m => m.setMap(null)); mapMarkers = [];
  const colours = ['#EA4335','#1a73e8','#34a853'];
  RECS.forEach((r, i) => {{
    const m = new google.maps.Marker({{
      position: {{lat:r.lat, lng:r.lng}}, map:gmap, title:r.name, zIndex:10+i,
      icon: {{
        path:'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
        fillColor:colours[i]||'#EA4335', fillOpacity:1,
        strokeColor:'#fff', strokeWeight:1.5, scale:1.8,
        anchor: new google.maps.Point(12,22),
      }},
      label: {{text:String(i+1), color:'white', fontSize:'10px', fontWeight:'bold'}},
    }});
    m.addListener('click', () => {{
      snapSheet('full');
      setTimeout(() => {{
        const cards = document.querySelectorAll('.rcard');
        if (cards[i]) cards[i].scrollIntoView({{behavior:'smooth', block:'start'}});
      }}, 350);
    }});
    mapMarkers.push(m);
  }});
  if (RECS.length > 0) {{
    const b = new google.maps.LatLngBounds();
    RECS.forEach(r => b.extend({{lat:r.lat, lng:r.lng}}));
    b.extend(CENTER);
    gmap.fitBounds(b, {{top:80, bottom:400, left:20, right:20}});
  }}
}}

(function() {{
  const s = document.createElement('script');
  s.src = `https://maps.googleapis.com/maps/api/js?key=${{MAP_KEY}}&callback=initMap`;
  s.async = true; s.defer = true;
  document.head.appendChild(s);
}})();

// ── HANDLE QUERY PARAMS FROM PREVIOUS RELOADS ─────────────────────────────────
// When triggerReload fires, Streamlit reads action/value from query_params and reruns.
// We don't need to do anything here — this is handled in Python above.

// ── SHEET HEIGHT & DRAG ───────────────────────────────────────────────────────
const TAB_H = 56, PEEK_H = 90;
const VH      = () => window.innerHeight;
const HALF_H  = () => Math.round(VH() * .50);
const FULL_H  = () => VH() - TAB_H - 72;
const sheet   = document.getElementById('sheet');
const content = document.getElementById('sheet-content');
const footer  = document.getElementById('sheet-footer');

const state = {{ view:'for-you', sheetSnap:'half', saved:{{}}, feedback:{{}}, history:[] }};

function snapHeight() {{
  return state.sheetSnap === 'peek' ? PEEK_H : state.sheetSnap === 'half' ? HALF_H() : FULL_H();
}}
function setSheetHeight(h, animate=true) {{
  sheet.style.transition = animate ? 'height .3s cubic-bezier(.4,0,.2,1)' : 'none';
  sheet.style.height = h + 'px';
}}
function snapSheet(snap, animate=true) {{
  state.sheetSnap = snap; setSheetHeight(snapHeight(), animate); render();
}}

let drag = null, contentDragCandidate = null;
const hw = document.getElementById('handle-wrap');
function onDragStart(e) {{
  const y = e.touches ? e.touches[0].clientY : e.clientY;
  drag = {{startY:y, startH:sheet.offsetHeight}};
  sheet.style.transition = 'none'; e.preventDefault();
}}
function onDragMove(e) {{
  if (!drag) return;
  const y = e.touches ? e.touches[0].clientY : e.clientY;
  const newH = Math.max(PEEK_H, Math.min(FULL_H(), drag.startH - (y - drag.startY)));
  sheet.style.height = newH + 'px'; e.preventDefault();
}}
function onDragEnd() {{
  if (!drag) return;
  const h = sheet.offsetHeight, half = HALF_H(), full = FULL_H();
  if (h < (PEEK_H + half) / 2) snapSheet('peek');
  else if (h < (half + full) / 2) snapSheet('half');
  else snapSheet('full');
  drag = null;
}}
hw.addEventListener('touchstart', onDragStart, {{passive:false}});
document.addEventListener('touchmove', onDragMove, {{passive:false}});
document.addEventListener('touchend', onDragEnd);
hw.addEventListener('mousedown', onDragStart);
document.addEventListener('mousemove', onDragMove);
document.addEventListener('mouseup', onDragEnd);

// Drag-to-collapse from content area when scrolled to top
content.addEventListener('touchstart', (e) => {{
  if (content.scrollTop <= 1 && state.sheetSnap === 'full') {{
    contentDragCandidate = {{startY:e.touches[0].clientY, startH:sheet.offsetHeight}};
  }}
}}, {{passive:false}});
content.addEventListener('touchmove', (e) => {{
  if (!contentDragCandidate) return;
  const dy = e.touches[0].clientY - contentDragCandidate.startY;
  if (dy > 6) {{
    drag = {{startY:contentDragCandidate.startY, startH:contentDragCandidate.startH}};
    contentDragCandidate = null;
    sheet.style.transition = 'none';
    e.preventDefault();
  }} else if (dy < -6) {{
    contentDragCandidate = null;
  }}
}}, {{passive:false}});
content.addEventListener('touchend', () => {{ contentDragCandidate = null; }}, {{passive:true}});

// ── TABS ──────────────────────────────────────────────────────────────────────
function setTab(tab) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tab)?.classList.add('active');
  state.view = tab === 'explore' ? 'for-you' : tab === 'you' ? 'you-history' : tab;
  state.sheetSnap = 'half'; setSheetHeight(snapHeight(), false); render();
}}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function stars(r) {{
  const f = Math.floor(r), h = (r-f) >= .5 ? 1 : 0;
  return '★'.repeat(f) + (h ? '½' : '') + '☆'.repeat(5-f-h);
}}
function priceFmt(l) {{
  return '€'.repeat(l||1) + '<span style="color:#dadce0">' + '€'.repeat(Math.max(0,4-(l||1))) + '</span>';
}}
function statusHtml(r) {{
  const cls = {{open:'status-open',closing_soon:'status-closing',closed:'status-closed'}}[r.status]||'status-open';
  const ico = {{open:'●',closing_soon:'⚠',closed:'✕'}}[r.status]||'●';
  return `<span class="${{cls}}">${{ico}} ${{r.hours}}</span>`;
}}
const RANK = ['🥇 Top pick','🥈 Runner-up','🥉 Also great'];

// ── CARD HTML ─────────────────────────────────────────────────────────────────
function cardHtml(r, i, teaser=false) {{
  const fb = state.feedback[r.name];
  const sv = state.saved[r.name];
  const d  = r.detail || {{}};
  const fbRow = teaser ? '' : (fb
    ? `<div style="padding:0 14px 10px;font-size:12px;color:var(--g3)">Marked: ${{fb}} — thanks!</div>`
    : `<div class="fb-row">
        <button class="fb-btn" onclick="setFb('${{r.name}}','👍')">👍 Interested</button>
        <button class="fb-btn" onclick="setFb('${{r.name}}','😐')">😐 Maybe</button>
        <button class="fb-btn" onclick="setFb('${{r.name}}','👎')">👎 Not for me</button>
      </div>`);
  const sd = teaser ? '' : `<div class="score-detail">
    <div style="font-size:11px;font-weight:600;color:var(--g2);margin-bottom:8px">Score breakdown</div>
    ${{[['Cuisine match',d.cuisine,40],['Rating quality',d.rating,30],['Price fit',d.price,20],['Distance',d.distance,10]].map(([l,v,m])=>
      `<div class="score-row"><span>${{l}}</span><span style="font-weight:600;color:var(--blue)">${{v}}/${{m}}</span></div>
       <div class="score-bar-track"><div class="score-bar-fill" style="width:${{Math.round(v/m*100)}}%"></div></div>`
    ).join('')}}
  </div>`;
  const actionsRow = teaser ? '' : `<div class="rcard-actions">
      <a href="${{r.maps_url}}" target="_blank" class="btn-dir">🧭 Directions</a>
      <button class="btn-save ${{sv?'saved':''}}" onclick="toggleSave('${{r.name}}')">${{sv?'🔖 Saved':'🔖 Save'}}</button>
    </div>`;
  return `<div class="rcard">
    <img src="${{r.photo}}" class="rcard-img" alt="${{r.name}}" loading="lazy">
    <div class="rcard-body">
      <div class="rcard-rank">${{RANK[i]||''}}</div>
      <div class="rcard-top"><div class="rcard-name">${{r.name}}</div><div class="match-badge">${{r.score}}% match</div></div>
      <div class="rcard-cuisine">${{r.cuisine}} · ${{r.neighborhood}}</div>
      <div class="meta-row">
        <div class="meta-item"><span class="stars">${{stars(r.rating)}}</span>&nbsp;${{r.rating}} (${{r.reviews.toLocaleString()}})</div>
        <div class="meta-item">🚶 ${{r.walk}} min · ${{r.distance}} km</div>
        <div class="meta-item">${{priceFmt(r.price)}}</div>
      </div>
      <div style="margin-bottom:8px">${{statusHtml(r)}}</div>
      <div class="why"><span style="font-size:13px;flex-shrink:0;margin-top:1px">✦</span><span>${{r.explanation||'…'}}</span></div>
    </div>
    ${{sd}}
    ${{actionsRow}}
    ${{fbRow}}
  </div>`;
}}

function setFb(name,val) {{
  state.feedback[name]=val;
  const r=RECS.find(r=>r.name===name);
  if(r&&!state.history.find(h=>h.name===name))
    state.history.push({{name:r.name,cuisine:r.cuisine,
      date:new Date().toLocaleDateString('en-GB',{{day:'numeric',month:'short'}}),
      intent:val,saved:!!state.saved[name]}});
  else {{ const e=state.history.find(h=>h.name===name); if(e) e.intent=val; }}
  render();
}}
function toggleSave(name) {{
  state.saved[name]=!state.saved[name];
  const e=state.history.find(h=>h.name===name);
  if(e) e.saved=state.saved[name];
  render();
}}
function goProfile()  {{ state.view='profile';  snapSheet('full'); }}
function goPipeline() {{ state.view='pipeline'; snapSheet('full'); }}
function goForYou() {{
  state.view='for-you';
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-explore')?.classList.add('active');
  snapSheet('half');
}}

// ── RENDER ────────────────────────────────────────────────────────────────────
function render() {{
  footer.innerHTML = '';
  content.style.webkitMaskImage=''; content.style.maskImage=''; content.style.overflowY='auto';
  const oldOv=document.getElementById('sheet-overlay-btn'); if(oldOv) oldOv.remove();
  const snap=state.sheetSnap, view=state.view;

  if(view==='for-you') {{
    const isHalf=snap!=='full';
    if(snap==='peek') {{
      content.innerHTML=`
        <div class="sh-header">
          <div class="sh-title">✦ For You <span class="badge">PERSONALISED</span></div>
          <div class="sh-sub">3 picks ready</div>
        </div>
        <div class="swipe-hint" onclick="snapSheet('half')">↑ Swipe up to see your picks</div>`;
      return;
    }}
    const cards=isHalf?cardHtml(RECS[0],0,true):RECS.map((r,i)=>cardHtml(r,i)).join('<div class="divider"></div>');

    if(isHalf) {{
      content.style.overflowY='hidden';
      // Gradient overlay floats above tab bar, creating the fade + button
      const ov=document.createElement('div');
      ov.id='sheet-overlay-btn';
      ov.style.cssText='position:absolute;bottom:56px;left:0;right:0;background:linear-gradient(transparent,rgba(255,255,255,.95) 40%,#fff 65%);padding:48px 0 12px;text-align:center;cursor:pointer;pointer-events:all;z-index:5';
      ov.innerHTML='<span style="font-size:11px;color:#80868b">↑ Show all picks</span>';
      ov.onclick=()=>snapSheet('full');
      sheet.appendChild(ov);
      content.innerHTML=`
        <div class="sh-header">
          <div class="sh-title">✦ For You <span class="badge">PERSONALISED</span></div>
          <div class="sh-sub">David · Pl. Catalunya · ${{NOW}}</div>
        </div>
        <div class="chip-strip">${{TAGS.map(t=>`<span class="chip">${{t}}</span>`).join('')}}</div>
        <div class="slabel">Your top pick right now</div>
        ${{cards}}`;
    }} else {{
      // Full state — collapse button in header + cards + collapse hint + profile/pipeline buttons
      const actions=`
        <div class="swipe-hint" onclick="snapSheet('half')" style="padding:14px 0 10px">↓ Collapse</div>
        <div style="padding:0 14px 16px;display:flex;gap:8px;">
          <button onclick="goProfile()" style="flex:1;border:1px solid var(--g5);border-radius:18px;padding:8px;font-size:13px;font-weight:500;background:var(--g7);color:var(--g2);cursor:pointer;font-family:Roboto,sans-serif">👤 My profile</button>
          <button onclick="goPipeline()" style="flex:1;border:1px solid var(--g5);border-radius:18px;padding:8px;font-size:13px;font-weight:500;background:var(--g7);color:var(--g2);cursor:pointer;font-family:Roboto,sans-serif">🔍 How it works</button>
        </div>`;
      content.innerHTML=`
        <div class="sh-header" style="align-items:flex-start">
          <div>
            <div class="sh-title">✦ For You <span class="badge">PERSONALISED</span></div>
            <div class="sh-sub">David · Pl. Catalunya · ${{NOW}}</div>
          </div>
          <button onclick="snapSheet('half')" style="flex-shrink:0;background:none;border:1px solid var(--g5);border-radius:16px;padding:4px 12px;font-size:12px;color:var(--g3);cursor:pointer;font-family:'Roboto',sans-serif;margin-top:2px">↓ Collapse</button>
        </div>
        <div class="chip-strip">${{TAGS.map(t=>`<span class="chip">${{t}}</span>`).join('')}}</div>
        <div class="slabel">Your picks right now</div>
        ${{cards}}${{actions}}`;
    }}
    return;
  }}

  if(view==='profile') {{
    content.innerHTML=`
      <div class="back-btn" onclick="goForYou()">← Back to picks</div>
      <div class="sh-header">
        <div class="sh-title">👤 David's Food Profile</div>
        <div class="sh-sub">Synthesized from your activity</div>
      </div>
      <div class="slabel">Cuisine affinities</div>
      ${{AF.map(a=>`<div class="aff-row">
        <div class="aff-label"><span>${{a.name}}</span><span style="font-weight:600;color:var(--blue)">${{a.pct}}%</span></div>
        <div class="aff-track"><div class="aff-fill" style="width:${{a.pct}}%"></div></div>
      </div>`).join('')}}
      <div class="slabel">Activity signals</div>
      <div class="metrics">
        <div class="metric"><div class="metric-val">47</div><div class="metric-lbl">Reviews</div></div>
        <div class="metric"><div class="metric-val">83</div><div class="metric-lbl">Visits</div></div>
        <div class="metric"><div class="metric-val">34</div><div class="metric-lbl">Searches</div></div>
        <div class="metric"><div class="metric-val">7</div><div class="metric-lbl">Saved</div></div>
      </div>
      <div class="slabel">Taste tags</div>
      <div class="chip-strip" style="flex-wrap:wrap;overflow:visible;padding-bottom:12px">
        ${{TAGS.map(t=>`<span class="chip">${{t}}</span>`).join('')}}
      </div>`;
    return;
  }}

  if(view==='pipeline') {{
    const sigs=[['📝','Review history','47 reviews · avg 4.1★ · 40% weight'],
      ['📍','Location history','83 restaurant visits · 35% weight'],
      ['🔖','Saved places','7 restaurants in lists · 25% weight'],
      ['🔎','Search history','34 food-related searches'],
      ['📅','Calendar & Gmail','Dinner reservations, booking confirmations']];
    const wts=[['Cuisine match',40],['Rating quality',30],['Price fit',20],['Distance',10]];
    content.innerHTML=`
      <div class="back-btn" onclick="goForYou()">← Back to picks</div>
      <div class="sh-header">
        <div class="sh-title">🔍 How we picked these</div>
        <div class="sh-sub">Signal pipeline · Scoring engine</div>
      </div>
      <div class="slabel">Input signals</div>
      ${{sigs.map(([ic,l,v])=>`<div class="pipe-row"><div class="pipe-icon">${{ic}}</div><div><div class="pipe-lbl">${{l}}</div><div class="pipe-val">${{v}}</div></div></div>`).join('')}}
      <div class="slabel">Scoring weights</div>
      ${{wts.map(([l,p])=>`<div class="aff-row"><div class="aff-label"><span>${{l}}</span><span style="font-weight:600;color:var(--blue)">${{p}}%</span></div><div class="aff-track"><div class="aff-fill" style="width:${{p}}%"></div></div></div>`).join('')}}`;
    return;
  }}

  if(view==='you-history') {{
    const hist=state.history;
    const rows=hist.length===0
      ?'<div class="empty">React to picks on the Explore tab to see history here.</div>'
      :hist.map(h=>`<div class="hist-row">
          <div class="hist-name">${{h.name}}</div>
          <div class="hist-meta">${{h.cuisine}} · ${{h.date}}</div>
          <div class="hist-badges">
            <span class="hist-badge intent">${{h.intent}}</span>
            ${{h.saved?'<span class="hist-badge svd">🔖 Saved</span>':''}}
          </div>
        </div>`).join('');
    content.innerHTML=`
      <div class="sh-header">
        <div class="sh-title">👤 Your Interactions</div>
        <div class="sh-sub">David · Engine performance</div>
      </div>
      <div class="metrics" style="margin-top:10px">
        <div class="metric"><div class="metric-val">${{hist.length}}</div><div class="metric-lbl">Shown</div></div>
        <div class="metric"><div class="metric-val">${{hist.filter(h=>h.intent==='👍').length}}</div><div class="metric-lbl">Interested</div></div>
        <div class="metric"><div class="metric-val">${{hist.filter(h=>state.saved[h.name]).length}}</div><div class="metric-lbl">Saved</div></div>
      </div>
      <div class="slabel">History</div>${{rows}}`;
    return;
  }}

  if(view==='contribute') {{
    content.innerHTML=`
      <div class="sh-header"><div class="sh-title">✏️ Contribute</div></div>
      <div class="empty">Add photos, write reviews, edit place info.</div>`;
  }}
}}

window.addEventListener('resize', () => setSheetHeight(snapHeight(), false));
document.addEventListener('DOMContentLoaded', () => {{
  setSheetHeight(snapHeight(), false);
  render();
}});
</script>
</body>
</html>"""

components.html(html, height=852, scrolling=False)

# ── Handle query_params set by the iframe chip buttons ────────────────────────
qp = st.query_params
action = qp.get("action", "")
value  = qp.get("value", "")

if action == "refresh":
    st.session_state.excluded = set()
    st.session_state.refresh  = True
    st.query_params.clear()
    st.rerun()
elif action == "mode" and value in ("all","date","cafe","casual","quick"):
    if value != st.session_state.mode:
        st.session_state.mode     = value
        st.session_state.excluded = set()
        st.session_state.refresh  = True
    st.query_params.clear()
    st.rerun()
elif action == "radius":
    try:
        new_r = int(value)
        if new_r != st.session_state.radius:
            st.session_state.radius   = new_r
            st.session_state.excluded = set()
            st.session_state.refresh  = True
    except Exception:
        pass
    st.query_params.clear()
    st.rerun()