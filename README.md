# HomeAnalytics

An open-source energy analytics platform for Home Assistant, providing comprehensive insight into home energy consumption, trends, and costs based on dynamic electricity prices.

## Overview

HomeAnalytics is a Home Assistant Add-on that helps you understand and optimize your home energy usage.

## Key Features

### Detailed Energy Reports

Generate comprehensive reports on energy consumption and costs:

- **Monthly Electricity Cost Reports**: Breakdown of costs for specific zones
- **Device-Specific Analysis**: Track energy consumption for individual appliances
- **Time-Period Analysis**: Compare consumption across months, seasons, or custom date ranges
- **Cost Optimization Insights**: Identify peak usage periods and potential savings

### Interactive Dashboard

A web-based dashboard providing key metrics and KPIs:

- **Real-time Energy Consumption**: Current usage across all monitored zones
- **Cost Tracking**: Daily, weekly, and monthly electricity expenditure
- **Trend Analysis**: Historical consumption patterns and comparisons
- **Price Impact Analysis**: How electricity price fluctuations affect total costs

### Explorative Analysis

Advanced analytics capabilities to answer questions like:

- "How much energy did the heat pump consume in June?"
- "How has energy consumption changed over time?"
- "What are the peak usage hours for each zone?"
- "How do electricity prices correlate with consumption patterns?"

## System Requirements

### Compatible Home Assistant Setup

HomeAnalytics works with any Home Assistant installation that provides:

- **Energy Sensors**: Power meters, consumption sensors, or smart plugs
- **Electricity Price Data**: Nordpool integration or similar dynamic pricing source
- **Zone Organization**: Logical grouping of devices by location

### Required Integrations

1. **Home Assistant** - Core platform for sensor data
2. **Nordpool Integration** - For electricity price data (or similar)
3. **Energy Sensors** - Power consumption measurements
4. **InfluxDB** - For historical data storage (recommended)

## Installation

### Home Assistant Add-on

1. Go to Settings → Add-ons → Add-on Store
2. Click "⋮" → "Repositories"
3. Add: `https://github.com/johanzander/home-analytics`
4. Find and install "HomeAnalytics"

### Configuration

```yaml
options:
  sensors:
    nordpool_price: "sensor.nordpool_kwh_se4_sek_2_10_025"

  influxdb:
    url: ""
    username: ""
    password: ""

  reports:
    auto_generate: true
    frequency: "monthly"
    export_format: "excel"
```

## Architecture

### Backend (Python/FastAPI)

- **Data Collection**: Interfaces with Home Assistant API and InfluxDB
- **Analytics Engine**: Processes energy data and generates reports
- **API Layer**: RESTful endpoints for frontend and external integrations

### Frontend (React)

- **Dashboard**: Interactive web interface with charts and KPIs
- **Report Viewer**: Display and export generated reports
- **Explorative Tools**: Query builder and data visualization

## Development

### Prerequisites

- Node.js 18+ (to build frontend)
- Python 3.11+ (to run backend)
- Docker (optional - Home Assistant builds the container for you)

### Quick Start

1. **Clone and setup:**

   ```bash
   git clone https://github.com/johanzander/home-analytics
   cd home-analytics
   python3 -m venv venv
   source venv/bin/activate
   pip install -r backend/requirements.txt
   cd frontend && npm install && cd ..
   ```

2. **Run development server:**

   ```bash
   ./dev-run.sh
   ```

   Visit `http://localhost:8082` for the app, `/docs` for API documentation.

### Project Structure

```text
home-analytics/
├── backend/
│   ├── app.py              # FastAPI application
│   ├── api.py              # API routes
│   ├── log_config.py       # Logging configuration
│   ├── requirements.txt    # Python dependencies
│   └── Dockerfile          # Local build Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # Main React component
│   │   └── main.jsx        # React entry point
│   ├── index.html          # HTML template
│   └── vite.config.js      # Vite configuration
├── config.yaml             # Home Assistant add-on config
├── Dockerfile              # GitHub Dockerfile (full build)
├── deploy.sh               # Local deployment script
└── package-addon.sh        # Packaging script
```

### Local Deployment

```bash
# Deploy to local Home Assistant instance
./deploy.sh
```

This packages the add-on and deploys to your HA add-ons directory (via SMB mount).

### API Endpoints

- `GET /` - Dashboard
- `GET /health` - Health check
- `GET /api/hello` - API status
- `GET /docs` - Interactive API documentation

## License

[MIT License](LICENSE)
