#!/bin/bash
# Script to deploy the HomeAnalytics add-on to a local Home Assistant instance

# Default target path, can be overridden by environment variable
TARGET_PATH=${TARGET_PATH:-"/Volumes/addons/home-analytics"}

if [ ! -d "$TARGET_PATH" ]; then
    echo "Creating target directory: $TARGET_PATH"
    mkdir -p "$TARGET_PATH"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create directory $TARGET_PATH"
        echo "Please check permissions or set TARGET_PATH environment variable"
        exit 1
    fi
fi

# Auto-increment patch version if deploying same version
if [ -f "$TARGET_PATH/config.yaml" ]; then
    CURRENT_VERSION=$(grep "^version:" "$TARGET_PATH/config.yaml" | cut -d'"' -f2)
    BUILD_VERSION=$(grep "^version:" "config.yaml" | cut -d'"' -f2)

    if [ "$CURRENT_VERSION" = "$BUILD_VERSION" ]; then
        echo "Same version detected ($BUILD_VERSION), auto-incrementing patch version..."

        # Extract version parts
        MAJOR=$(echo $BUILD_VERSION | cut -d. -f1)
        MINOR=$(echo $BUILD_VERSION | cut -d. -f2)
        PATCH=$(echo $BUILD_VERSION | cut -d. -f3)

        # Increment patch version
        NEW_PATCH=$((PATCH + 1))
        NEW_VERSION="${MAJOR}.${MINOR}.${NEW_PATCH}"

        echo "Updating version: $BUILD_VERSION → $NEW_VERSION"
        sed -i '' "s/version: \"$BUILD_VERSION\"/version: \"$NEW_VERSION\"/" config.yaml
        echo "Updated config.yaml"
    fi
fi

# Build first to ensure latest version
echo "Building add-on..."
./package-addon.sh

echo "Deploying to $TARGET_PATH..."


# Use rsync to exclude unwanted files
# --inplace: avoid temp files (needed for SMB/mounted volumes)
# --no-times/--no-perms: don't try to set attributes the filesystem doesn't support
rsync -rv --delete --inplace --no-times --no-perms --no-owner --no-group \
  --exclude='.DS_Store' \
  --exclude='*.pyc' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='.git*' \
  --exclude='*.tmp' \
  --exclude='*.log' \
  build/home-analytics/ "$TARGET_PATH/"


echo "Deployment complete!"

# Check if version was updated
if [ -f "$TARGET_PATH/config.yaml" ]; then
    VERSION=$(grep "^version:" "$TARGET_PATH/config.yaml" | cut -d' ' -f2 | tr -d '"')
    echo "Deployed version: $VERSION"
    echo ""
    echo "📋 Next steps:"
    echo "1. Go to Home Assistant → Settings → Add-ons"
    echo "2. Find 'HomeAnalytics Add-on'"
    echo "3. Click 'Reload' or restart the add-on"
    echo "4. Verify version shows: $VERSION"
else
    echo "⚠️  Could not verify deployment version"
fi