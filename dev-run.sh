#!/bin/bash
# Development startup script for HomeAnalytics Add-on

set -e

# Cleanup function to kill background processes on exit
cleanup() {
  echo ""
  echo "🛑 Shutting down development servers..."
  kill $(jobs -p) 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "🚀 Starting HomeAnalytics Add-on Development Server"

# Check if .env exists (optional for this template)
if [ -f .env ]; then
  echo "📝 Loading environment from .env..."
  set -a
  source .env
  set +a
else
  echo "ℹ️  No .env file found. Using default settings."
fi

# Kill any existing frontend dev server on port 5173
FRONTEND_PORT=5173
if lsof -i :$FRONTEND_PORT -t >/dev/null 2>&1; then
  echo "⚠️  Port $FRONTEND_PORT is in use. Killing existing process..."
  lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# Start frontend dev-server (hot-reload)
echo "📦 Starting frontend dev-server (hot-reload) on port $FRONTEND_PORT..."
cd frontend
npm install
npm run dev &
cd ..

# Set default environment variables if not set
export HA_URL="${HA_URL:-http://localhost:8123}"
export HA_TOKEN="${HA_TOKEN:-}"

# Display configuration
echo "🏠 Home Assistant URL: $HA_URL"
echo "🔑 Token configured: $(if [ -n "$HA_TOKEN" ]; then echo 'Yes'; else echo 'No'; fi)"

# Wait for port 8082 to be free
PORT=8082
MAX_ATTEMPTS=10
ATTEMPT=0

while lsof -i :$PORT -t >/dev/null; do
  ATTEMPT=$((ATTEMPT + 1))
  if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    echo "❌ Port $PORT is still in use after $MAX_ATTEMPTS attempts. Exiting."
    exit 1
  fi
  echo "⚠️  Port $PORT is already in use. Attempting to kill existing process... (Attempt $ATTEMPT/$MAX_ATTEMPTS)"
  lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
  sleep 1
done

if [ $ATTEMPT -gt 0 ]; then
  echo "✅ Port $PORT is now free."
fi

# Start the development server
echo "🌐 Starting server on http://localhost:8082"
cd backend
source ../venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8082 --reload