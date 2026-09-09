ARG BUILD_FROM
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
    org.label-schema.vcs-ref=${BUILD_REF}

# Install requirements for add-on (no Node.js - frontend is pre-built).
# Python and pip come from the base image (/usr/local/bin). Do NOT apk add
# python3/py3-pip here: on the HA base-python images that installs Alpine's
# own interpreter at /usr/bin alongside it, and which one `python3 -m venv`
# picks then depends on PATH order. gcc/musl-dev stay for source builds.
RUN apk add --no-cache gcc musl-dev bash

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
