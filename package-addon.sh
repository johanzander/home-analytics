#!/bin/bash
set -e

# Package HomeAnalytics add-on for local Home Assistant installation
# For GitHub/HACS installation, Home Assistant builds directly from the repo

echo "🔨 Building HomeAnalytics add-on package..."

# Clean previous build
echo "Cleaning old build directory..."
BUILD_DIR="./build/home-analytics"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Build frontend first
echo "📦 Building frontend..."
cd frontend
npm ci
npm run build
cd ..

# Copy Dockerfile and configuration
# NOTE: Use backend/Dockerfile for local builds (no npm ci, uses pre-built frontend)
# The root Dockerfile is for GitHub/HACS builds where frontend is built from source
echo "📦 Copying Dockerfile and configuration..."
cp backend/Dockerfile "$BUILD_DIR/Dockerfile"
cp config.yaml "$BUILD_DIR/"
cp build.json "$BUILD_DIR/"

# Copy backend files (preserve backend/ structure to match root Dockerfile paths)
echo "📦 Copying backend files..."
mkdir -p "$BUILD_DIR/backend"
cp backend/app.py "$BUILD_DIR/backend/"
cp backend/api.py "$BUILD_DIR/backend/"
cp backend/log_config.py "$BUILD_DIR/backend/"
cp backend/requirements.txt "$BUILD_DIR/backend/"
cp backend/run.sh "$BUILD_DIR/backend/"
cp backend/sensors.yaml "$BUILD_DIR/backend/"

# Copy backend services (excluding __pycache__)
echo "📦 Copying backend services..."
mkdir -p "$BUILD_DIR/backend/services"
cp backend/services/*.py "$BUILD_DIR/backend/services/"

# Copy built frontend files
echo "📦 Copying frontend files..."
mkdir -p "$BUILD_DIR/frontend"
cp -r frontend/dist/* "$BUILD_DIR/frontend/"

# Create repository structure
echo "📦 Creating repository structure..."
mkdir -p ./build/repository/home-analytics
cp -r "$BUILD_DIR"/* ./build/repository/home-analytics/

# Create repository.json
cat > ./build/repository.json <<EOF
{
  "name": "HomeAnalytics Add-on Repository",
  "url": "https://github.com/johanzander/home-analytics",
  "maintainer": "Johan Zander <johanzander@gmail.com>"
}
EOF

echo "✅ Package created in ./build/"
