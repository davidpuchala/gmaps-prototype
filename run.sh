#!/bin/bash
# ── For You · Barcelona — one-command launcher ──────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_PORT=8501
WRAPPER_PORT=8502

echo "🚀 Starting For You app..."

# Kill anything on our ports
lsof -ti tcp:$APP_PORT | xargs kill -9 2>/dev/null
lsof -ti tcp:$WRAPPER_PORT | xargs kill -9 2>/dev/null
sleep 0.5

# Start Streamlit in the background
cd "$SCRIPT_DIR"
streamlit run app.py --server.port $APP_PORT --server.headless true > /tmp/streamlit.log 2>&1 &
STREAMLIT_PID=$!

# Serve the wrapper HTML over HTTP (avoids file:// browser restrictions + session crashes)
python3 -m http.server $WRAPPER_PORT --directory "$SCRIPT_DIR" > /dev/null 2>&1 &
HTTP_PID=$!

echo "⏳ Waiting for Streamlit..."
for i in $(seq 1 20); do
  if curl -s "http://localhost:$APP_PORT" > /dev/null 2>&1; then
    echo "✅ Streamlit ready"
    break
  fi
  sleep 1
done

# Open in Chrome (avoids Firefox session restore crashes)
echo "📱 Opening iPhone frame..."
if command -v google-chrome &>/dev/null; then
  google-chrome "http://localhost:$WRAPPER_PORT/iphone_wrapper.html" &
elif command -v /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome &>/dev/null; then
  open -a "Google Chrome" "http://localhost:$WRAPPER_PORT/iphone_wrapper.html"
else
  # Fallback: system default browser via http (not file://)
  open "http://localhost:$WRAPPER_PORT/iphone_wrapper.html"
fi

echo ""
echo "✅ Running:"
echo "   App    → http://localhost:$APP_PORT"
echo "   Frame  → http://localhost:$WRAPPER_PORT/iphone_wrapper.html"
echo ""
echo "Press Ctrl+C to stop everything."

trap "kill $STREAMLIT_PID $HTTP_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait $STREAMLIT_PID