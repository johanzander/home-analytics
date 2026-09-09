ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.22

# Build the frontend natively to avoid QEMU npm timeouts: $BUILDPLATFORM is
# the host doing the build (amd64 on CI runners, arm64 on an Apple Silicon
# dev machine), never the emulated target. The stage emits plain JS, so its
# arch does not matter to the image.
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend-builder
ARG BUILD_VERSION
WORKDIR /tmp/frontend
RUN echo "Building frontend for version ${BUILD_VERSION}"
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM $BUILD_FROM

# Set version labels
ARG BUILD_VERSION
ARG BUILD_DATE
ARG BUILD_REF

# Labels
LABEL \
    io.hass.name="HomeAnalytics Add-on" \
    io.hass.description="A Home Assistant Add-on for home energy consumption and cost analytics" \
    io.hass.version=${BUILD_VERSION} \
    io.hass.type="addon" \
    io.hass.arch="aarch64,amd64" \
    maintainer="Johan Zander <johanzander@gmail.com>" \
    org.label-schema.build-date=${BUILD_DATE} \
    org.label-schema.description="A Home Assistant Add-on for home energy consumption and cost analytics" \
    org.label-schema.name="HomeAnalytics Add-on" \
    org.label-schema.schema-version="1.0" \
    org.label-schema.vcs-ref=${BUILD_REF} \
    org.label-schema.vcs-url="https://github.com/johanzander/home-analytics"

# Python and pip come from the base image (/usr/local/bin). Do NOT apk add
# python3/py3-pip here: on the HA base-python images that installs Alpine's
# own interpreter at /usr/bin alongside it, and which one `python3 -m venv`
# picks then depends on PATH order. gcc/musl-dev stay for source builds.
RUN apk add --no-cache \
    gcc \
    musl-dev \
    bash

# Set working directory
WORKDIR /app

# Copy Python application files from backend directory
COPY backend/app.py backend/api.py backend/log_config.py backend/requirements.txt ./
COPY backend/sensors.yaml ./

# Copy services directory
COPY backend/services/ ./services/

# Copy pre-built frontend from native build stage
COPY --from=frontend-builder /tmp/frontend/dist/ /app/frontend/

# Copy run script
COPY backend/run.sh ./

# Create and use virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Install Python requirements in the virtual environment
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Make scripts executable
RUN chmod a+x /app/run.sh

# Expose the port
EXPOSE 8082

# Launch application
CMD ["/usr/bin/with-contenv", "bash", "/app/run.sh"]
