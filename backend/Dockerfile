ARG BUILD_FROM
FROM $BUILD_FROM

# Set version labels
ARG BUILD_VERSION
ARG BUILD_DATE
ARG BUILD_REF

# Labels
LABEL \
    io.hass.name="HomeAnalytics Add-on" \
    io.hass.description="A generic Home Assistant Add-on template with Python backend and React frontend" \
    io.hass.version=${BUILD_VERSION} \
    io.hass.type="addon" \
    io.hass.arch="aarch64,amd64,armhf,armv7,i386" \
    maintainer="Your Name <your.email@example.com>" \
    org.label-schema.build-date=${BUILD_DATE} \
    org.label-schema.description="A generic Home Assistant Add-on template with Python backend and React frontend" \
    org.label-schema.name="HomeAnalytics Add-on" \
    org.label-schema.schema-version="1.0" \
    org.label-schema.vcs-ref=${BUILD_REF}

# Install requirements for add-on (no Node.js - frontend is pre-built)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    gcc \
    musl-dev \
    bash

# Set working directory
WORKDIR /app

# Copy Python application files from backend directory
COPY backend/app.py backend/api.py backend/log_config.py backend/requirements.txt ./
COPY backend/sensors.yaml ./

COPY backend/services/ ./services/

# Copy run script
COPY backend/run.sh ./

# Copy pre-built frontend (already built by package-addon.sh)
COPY frontend/ /app/frontend/

# Create and use virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Install Python requirements in the virtual environment
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Make scripts executable
RUN chmod a+x /app/run.sh

# Expose the port
EXPOSE 8082

# Launch application
CMD ["/usr/bin/with-contenv", "bash", "/app/run.sh"]
