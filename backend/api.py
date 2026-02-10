"""
API Router for Home Analytics Add-on

Exposes endpoints to query energy data.
"""

from calendar import monthrange
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response
from loguru import logger
from services.influx_service import InfluxService


# ---------------------------------------------------------------------------
# In-memory cache for _compute_month_data results
# Key: (year, month) → {"data": <result dict>, "cached_at": <datetime>}
# Past months are cached indefinitely; current month uses a short TTL.
# ---------------------------------------------------------------------------
_month_cache: dict[tuple[int, int], dict[str, Any]] = {}
_CURRENT_MONTH_TTL_SECONDS = 300  # 5 minutes for the current (incomplete) month


# Load options from config.yaml (dev/prod)
def load_options_config() -> dict:
    import json
    import os

    # /data/options.json in prod, config.yaml in dev
    options_path = Path("/data/options.json")
    config_path = Path(__file__).parent.parent / "config.yaml"
    options = {}
    if options_path.exists():
        with open(options_path) as f:
            options = json.load(f)
    elif config_path.exists():
        import yaml

        with open(config_path) as f:
            config = yaml.safe_load(f)
        options = config.get("options", {})
    # Always allow secrets from env to override, using nested influx section
    if "influx" not in options:
        options["influx"] = {}
    influx = options["influx"]
    influx["url"] = os.getenv("INFLUXDB_URL", influx.get("url", ""))
    influx["username"] = os.getenv("INFLUXDB_USERNAME", influx.get("username", ""))
    influx["password"] = os.getenv("INFLUXDB_PASSWORD", influx.get("password", ""))
    influx["bucket"] = os.getenv(
        "INFLUXDB_BUCKET", influx.get("bucket", "home_assistant/autogen")
    )
    options["influx"] = influx
    return options


options = load_options_config()


def load_sensors_config() -> dict[str, str]:
    """Load sensor entity IDs from options hierarchy."""
    return {
        "gardshus": options["sensors"].get("gardshus", ""),
        "salong": options["sensors"].get("salong", ""),
        "electricity_price": options["sensors"].get("electricity_price", ""),
        "energy_consumption": options["sensors"].get("energy_consumption", ""),
    }


def load_cost_config() -> dict[str, Any]:
    """Load cost rates from options hierarchy."""
    return {
        "areas": {
            "gardshus": {
                "name": options.get("gardshus_name", "Gårdshus"),
                "eon_abonnemang_bidrag_inkl_moms": options.get(
                    "gardshus_eon_contribution", 165.00
                ),
            },
            "salong": {
                "name": options.get("salong_name", "Salong"),
                "eon_abonnemang_bidrag_inkl_moms": options.get(
                    "salong_eon_contribution", 0
                ),
            },
        },
        "energy_supplier": {
            "abonnemang_ex_moms": options.get("tibber_subscription_ex_moms", 39.20),
            "markup_per_kwh_ex_moms": options.get(
                "tibber_markup_per_kwh_ex_moms", 0.068
            ),
        },
        "utility_operator": {
            "overforingsavgift_per_kwh": options.get(
                "eon_transfer_fee_per_kwh", 0.2456
            ),
            "energiskatt_per_kwh": options.get("eon_energy_tax_per_kwh", 0.439),
            "abonnemang_ex_moms": options.get("eon_subscription_ex_moms", 805.00),
        },
        "common": {
            "moms_rate": options.get("vat_rate", 0.25),
        },
    }


def calculate_area_invoice(
    consumption_kwh: float,
    hourly_tibber_cost: float,
    area_key: str,
    cost_config: dict,
) -> dict:
    """
    Calculate invoice for a single area (Gårdshus or Salong).

    Areas only pay for their consumption + any subscription contribution.
    Full subscription fees are shown in totals only.
    """
    area_config = cost_config.get("areas", {}).get(area_key, {})
    utility_operator = cost_config.get("utility_operator", {})
    moms_rate = cost_config.get("common", {}).get("moms_rate", 0.25)

    # === TIBBER (el-leverantör) ===
    # Electricity cost - convert from inkl. moms to ex. moms
    el_cost_inkl_moms = hourly_tibber_cost
    el_cost_ex_moms = el_cost_inkl_moms / (1 + moms_rate)

    # Areas don't pay Tibber subscription separately (shown in total only)
    tibber_subtotal_ex_moms = el_cost_ex_moms
    tibber_moms = tibber_subtotal_ex_moms * moms_rate
    energy_consumption_inkl_moms = tibber_subtotal_ex_moms + tibber_moms

    # === E.ON (nätägare) ===
    # Grid fees based on consumption (ex. moms)
    if (
        "overforingsavgift_per_kwh" not in utility_operator
        or "energiskatt_per_kwh" not in utility_operator
    ):
        raise ValueError(
            "Missing E.ON rates in config: overforingsavgift_per_kwh or energiskatt_per_kwh"
        )
    overforingsavgift_ex_moms = (
        consumption_kwh * utility_operator["overforingsavgift_per_kwh"]
    )
    energiskatt_ex_moms = consumption_kwh * utility_operator["energiskatt_per_kwh"]

    # Contribution to E.ON subscription (stored as inkl. moms, convert to ex. moms)
    abonnemang_bidrag_inkl_moms = area_config.get("eon_abonnemang_bidrag_inkl_moms", 0)
    abonnemang_bidrag_ex_moms = abonnemang_bidrag_inkl_moms / (1 + moms_rate)

    # E.ON totals for this area
    eon_subtotal_ex_moms = (
        overforingsavgift_ex_moms + energiskatt_ex_moms + abonnemang_bidrag_ex_moms
    )
    eon_moms = eon_subtotal_ex_moms * moms_rate
    eon_total_inkl_moms = eon_subtotal_ex_moms + eon_moms

    # === AREA TOTAL ===
    total_inkl_moms = energy_consumption_inkl_moms + eon_total_inkl_moms

    return {
        "consumption_kwh": round(consumption_kwh, 2),
        "tibber": {
            "el_cost_ex_moms": round(el_cost_ex_moms, 2),
            "subtotal_ex_moms": round(tibber_subtotal_ex_moms, 2),
            "moms": round(tibber_moms, 2),
            "total_inkl_moms": round(energy_consumption_inkl_moms, 2),
        },
        "eon": {
            "overforingsavgift_ex_moms": round(overforingsavgift_ex_moms, 2),
            "energiskatt_ex_moms": round(energiskatt_ex_moms, 2),
            "abonnemang_bidrag_ex_moms": round(abonnemang_bidrag_ex_moms, 2),
            "subtotal_ex_moms": round(eon_subtotal_ex_moms, 2),
            "moms": round(eon_moms, 2),
            "total_inkl_moms": round(eon_total_inkl_moms, 2),
        },
        "el_cost_inkl_moms": round(el_cost_inkl_moms, 2),
        "total_inkl_moms": round(total_inkl_moms, 2),
    }


def calculate_totals(gardshus: dict, salong: dict, cost_config: dict) -> dict:
    """
    Calculate total invoice (full electricity bill).

    Totals include full subscription fees (not split per area).
    """
    energy_supplier = cost_config.get("energy_supplier", {})
    utility_operator = cost_config.get("utility_operator", {})
    moms_rate = cost_config.get("common", {}).get("moms_rate", 0.25)

    # Total consumption (will be overwritten by Tibber sensor in main function)
    total_consumption = gardshus["consumption_kwh"] + salong["consumption_kwh"]

    # === TIBBER TOTAL ===
    # Sum of electricity costs + full Tibber subscription
    tibber_el_cost_ex_moms = (
        gardshus["tibber"]["el_cost_ex_moms"] + salong["tibber"]["el_cost_ex_moms"]
    )
    tibber_abonnemang_ex_moms = energy_supplier.get("abonnemang_ex_moms", 39.20)
    tibber_subtotal_ex_moms = tibber_el_cost_ex_moms + tibber_abonnemang_ex_moms
    tibber_moms = tibber_subtotal_ex_moms * moms_rate
    energy_consumption_inkl_moms = tibber_subtotal_ex_moms + tibber_moms

    # === E.ON TOTAL ===
    # Sum of grid fees + full E.ON subscription
    eon_overforingsavgift = (
        gardshus["eon"]["overforingsavgift_ex_moms"]
        + salong["eon"]["overforingsavgift_ex_moms"]
    )
    eon_energiskatt = (
        gardshus["eon"]["energiskatt_ex_moms"] + salong["eon"]["energiskatt_ex_moms"]
    )
    if "abonnemang_ex_moms" not in utility_operator:
        raise ValueError("Missing E.ON abonnemang_ex_moms in config")
    eon_abonnemang_ex_moms = utility_operator["abonnemang_ex_moms"]
    eon_subtotal_ex_moms = (
        eon_overforingsavgift + eon_energiskatt + eon_abonnemang_ex_moms
    )
    eon_moms = eon_subtotal_ex_moms * moms_rate
    eon_total_inkl_moms = eon_subtotal_ex_moms + eon_moms

    # === GRAND TOTAL ===
    total_inkl_moms = energy_consumption_inkl_moms + eon_total_inkl_moms

    return {
        "consumption_kwh": round(total_consumption, 2),
        "tibber": {
            "el_cost_ex_moms": round(tibber_el_cost_ex_moms, 2),
            "abonnemang_ex_moms": round(tibber_abonnemang_ex_moms, 2),
            "subtotal_ex_moms": round(tibber_subtotal_ex_moms, 2),
            "moms": round(tibber_moms, 2),
            "total_inkl_moms": round(energy_consumption_inkl_moms, 2),
        },
        "eon": {
            "overforingsavgift_ex_moms": round(eon_overforingsavgift, 2),
            "energiskatt_ex_moms": round(eon_energiskatt, 2),
            "abonnemang_ex_moms": round(eon_abonnemang_ex_moms, 2),
            "subtotal_ex_moms": round(eon_subtotal_ex_moms, 2),
            "moms": round(eon_moms, 2),
            "total_inkl_moms": round(eon_total_inkl_moms, 2),
        },
        "total_inkl_moms": round(total_inkl_moms, 2),
    }


MONTHS_SV = [
    "Januari", "Februari", "Mars", "April", "Maj", "Juni",
    "Juli", "Augusti", "September", "Oktober", "November", "December",
]


def _compute_month_data(
    year: int, month: int, influx: InfluxService
) -> dict[str, Any] | None:
    """Core monthly computation shared between report and invoice views.

    Queries sensor data, handles gaps via linear interpolation, computes
    per-area consumption and costs.  Returns all computed data or None
    if no sensor data is available for the period.

    Results are cached in memory.  Past months are cached indefinitely;
    the current month is cached for 5 minutes.
    """
    now = datetime.now()
    key = (year, month)
    is_current_month = year == now.year and month == now.month

    # Check cache
    if key in _month_cache:
        entry = _month_cache[key]
        if is_current_month:
            age = (now - entry["cached_at"]).total_seconds()
            if age < _CURRENT_MONTH_TTL_SECONDS:
                logger.debug(f"Cache hit (current month, age={age:.0f}s): {year}-{month:02d}")
                return entry["data"]
        else:
            logger.debug(f"Cache hit (past month): {year}-{month:02d}")
            return entry["data"]

    last_day = monthrange(year, month)[1]
    start_date = datetime(year, month, 1, 0, 0, 0)
    end_date = datetime(year, month, last_day, 23, 0, 0)

    sensors = load_sensors_config()
    sensor_list = list(sensors.values())
    df = influx.query_specific_sensors(
        start_date=start_date, end_date=end_date, sensor_list=sensor_list
    )

    if df.empty:
        if not is_current_month:
            _month_cache[key] = {"data": None, "cached_at": datetime.now()}
        return None

    # Check that at least the meter sensors are present
    has_gardshus = sensors["gardshus"] in df.columns
    has_salong = sensors["salong"] in df.columns
    if not has_gardshus and not has_salong:
        if not is_current_month:
            _month_cache[key] = {"data": None, "cached_at": datetime.now()}
        return None

    # Handle zeros as missing data (sensor outages) for meter readings
    for sensor_name in [sensors["gardshus"], sensors["salong"]]:
        if sensor_name not in df.columns:
            continue
        mask = df[sensor_name] == 0
        if mask.any():
            logger.debug(
                f"Replacing {mask.sum()} zero values with NaN for {sensor_name}"
            )
            df.loc[mask, sensor_name] = pd.NA

    # Track which hours have missing meter data (before interpolation)
    gardshus_estimated = (
        df[sensors["gardshus"]].isna() if has_gardshus else pd.Series(dtype=bool)
    )
    salong_estimated = (
        df[sensors["salong"]].isna() if has_salong else pd.Series(dtype=bool)
    )

    # Linear interpolation spreads gap consumption evenly across missing hours
    for sensor_name in [sensors["gardshus"], sensors["salong"]]:
        if sensor_name in df.columns:
            df[sensor_name] = (
                df[sensor_name].interpolate(method="linear").ffill().bfill()
            )

    # Extract meter readings
    gardshus_last = float(df[sensors["gardshus"]].iloc[-1]) if has_gardshus else None
    salong_last = float(df[sensors["salong"]].iloc[-1]) if has_salong else None

    # Calculate hourly consumption (delta from cumulative meter readings)
    if has_gardshus:
        df["gardshus_consumption"] = df[sensors["gardshus"]].diff()
    if has_salong:
        df["salong_consumption"] = df[sensors["salong"]].diff()

    # Get electricity price (already in SEK/kWh inkl moms)
    df["price"] = df[sensors["electricity_price"]] if sensors["electricity_price"] in df.columns else 0

    # Load cost configuration
    cost_config = load_cost_config()
    moms_rate = cost_config.get("common", {}).get("moms_rate", 0.25)
    tibber_markup_per_kwh_ex_moms = cost_config.get("energy_supplier", {}).get(
        "markup_per_kwh_ex_moms", 0.068
    )

    # Calculate spot and markup for each area
    for area in ["gardshus", "salong"]:
        if f"{area}_consumption" not in df.columns:
            continue
        df[f"{area}_spot"] = df[f"{area}_consumption"] * (
            df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df[f"{area}_markup"] = (
            df[f"{area}_consumption"] * tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df[f"{area}_cost"] = df[f"{area}_spot"] + df[f"{area}_markup"]

    # Calculate area totals
    gardshus_kwh = float(df["gardshus_consumption"].sum()) if has_gardshus else 0
    salong_kwh = float(df["salong_consumption"].sum()) if has_salong else 0
    gardshus_el_cost = float(df["gardshus_cost"].sum()) if has_gardshus else 0
    salong_el_cost = float(df["salong_cost"].sum()) if has_salong else 0

    # Calculate per-area invoices (includes E.ON grid fees)
    gardshus_invoice = calculate_area_invoice(
        consumption_kwh=gardshus_kwh,
        hourly_tibber_cost=gardshus_el_cost,
        area_key="gardshus",
        cost_config=cost_config,
    ) if has_gardshus else None

    salong_invoice = calculate_area_invoice(
        consumption_kwh=salong_kwh,
        hourly_tibber_cost=salong_el_cost,
        area_key="salong",
        cost_config=cost_config,
    ) if has_salong else None

    result = {
        "start_date": start_date,
        "end_date": end_date,
        "df": df,
        "sensors": sensors,
        "cost_config": cost_config,
        "gardshus_invoice": gardshus_invoice,
        "salong_invoice": salong_invoice,
        "gardshus_meter_reading": round(gardshus_last, 1) if gardshus_last is not None else None,
        "salong_meter_reading": round(salong_last, 1) if salong_last is not None else None,
        "gardshus_estimated": gardshus_estimated,
        "salong_estimated": salong_estimated,
    }

    # Store in cache
    _month_cache[key] = {"data": result, "cached_at": datetime.now()}
    logger.debug(f"Cached month data: {year}-{month:02d}")

    return result


router = APIRouter()


# Instantiate services with config options
influx_service: InfluxService | None = None
startup_error: str = ""
try:
    influx_service = InfluxService(options)
except ValueError as e:
    startup_error = str(e)


def get_influx_service() -> InfluxService:
    """Get the InfluxDB service, raising an error if not initialized."""
    if influx_service is None:
        raise HTTPException(
            status_code=503,
            detail=f"InfluxDB service not initialized: {startup_error}",
        )
    return influx_service


@router.on_event("startup")
async def startup_event() -> None:
    if influx_service is None:
        # Log the error at startup
        logger.error(f"InfluxDB service could not be initialized: {startup_error}")


@router.get("/hello")
async def hello_api() -> dict:
    """Return a hello message."""
    return {"message": "Hello from API!", "version": "0.1.0"}


@router.post("/cache/clear")
async def clear_cache() -> dict:
    """Clear the in-memory month data cache."""
    count = len(_month_cache)
    _month_cache.clear()
    logger.info(f"Cleared {count} cached month entries")
    return {"cleared": count}


@router.get("/energy/history")
async def get_energy_history(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> Response:
    """
    Fetch historical energy data for the configured sensors.
    """
    if start_date is None:
        start_date = Query(..., description="Start date in ISO format")
    if end_date is None:
        end_date = Query(..., description="End date in ISO format")

    if start_date >= end_date:
        raise HTTPException(
            status_code=400, detail="start_date must be before end_date"
        )

    df = get_influx_service().query_energy_data(
        start_date=start_date, end_date=end_date
    )

    if df.empty:
        return Response(content="[]", media_type="application/json")

    # Convert DataFrame to JSON. orient='split' is efficient for timeseries.
    json_data = df.to_json(orient="split", date_format="iso")

    return Response(content=json_data, media_type="application/json")


@router.get("/sensors")
async def get_sensors() -> list[str]:
    """Return the list of sensors being monitored."""
    return get_influx_service().get_sensors()


@router.get("/report/monthly")
async def get_monthly_report(
    year: int = Query(..., ge=2020, le=2100, description="Year (e.g., 2025)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
) -> dict:
    """
    Get monthly energy consumption and cost report for Gardshus and Salong.

    Returns consumption in kWh and cost in SEK for the specified month.
    """
    logger.info(f"Generating monthly report for {year}-{month:02d}")

    # Use shared monthly computation
    computed = _compute_month_data(year, month, get_influx_service())
    if computed is None:
        raise HTTPException(status_code=404, detail="No data available for this period")

    df = computed["df"]
    sensors = computed["sensors"]
    cost_config = computed["cost_config"]
    gardshus_invoice = computed["gardshus_invoice"]
    salong_invoice = computed["salong_invoice"]
    gardshus_estimated = computed["gardshus_estimated"]
    salong_estimated = computed["salong_estimated"]
    start_date = computed["start_date"]
    end_date = computed["end_date"]

    # Check that all required sensors are present for the full report
    missing = [name for name, sensor in sensors.items() if sensor not in df.columns]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Missing sensors in data: {missing}. Available: {list(df.columns)}",
        )

    if gardshus_invoice is None or salong_invoice is None:
        raise HTTPException(status_code=404, detail="Missing area data for report")

    moms_rate = cost_config.get("common", {}).get("moms_rate", 0.25)
    tibber_markup_per_kwh_ex_moms = cost_config.get("energy_supplier", {}).get(
        "markup_per_kwh_ex_moms", 0.068
    )

    # Area totals from shared computation
    gardshus_spot = float(df["gardshus_spot"].sum())
    gardshus_markup = float(df["gardshus_markup"].sum())
    salong_spot = float(df["salong_spot"].sum())
    salong_markup = float(df["salong_markup"].sum())

    # Calculate Tibber total for the property (from Tibber sensor)
    energy_first = df[sensors["energy_consumption"]].iloc[0]
    energy_last = df[sensors["energy_consumption"]].iloc[-1]
    energy_total_kwh = energy_last - energy_first
    energy_total_spot = (
        (df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate))
        * (df[sensors["energy_consumption"]].diff())
    ).sum()
    energy_total_markup = (
        df[sensors["energy_consumption"]].diff()
        * tibber_markup_per_kwh_ex_moms
        * (1 + moms_rate)
    ).sum()
    # energy_total_cost is not used, calculation is split into spot and markup

    # Calculate average spot price (ex moms) based on Tibber sensor
    # This matches the spot_ex_moms calculation for the total, but as an average per kWh
    # Only use periods with positive consumption to avoid NaN/inf
    energy_diffs = df[sensors["energy_consumption"]].diff()
    valid = energy_diffs > 0
    # Spot price per hour (ex moms)
    spot_per_hour = (df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate)) / (
        1 + moms_rate
    )
    weighted_spot_sum = (spot_per_hour[valid] * energy_diffs[valid]).sum()
    total_kwh = energy_diffs[valid].sum()
    avg_spot_ex_moms = weighted_spot_sum / total_kwh if total_kwh > 0 else None

    # Area invoices already computed by _compute_month_data (same calculate_area_invoice)

    # Calculate totals (includes full subscription fees)
    # Use Tibber sensor for total consumption
    totals = calculate_totals(gardshus_invoice, salong_invoice, cost_config)
    # Use Tibber sensor for total consumption and E.ON grid fees
    totals["consumption_kwh"] = round(energy_total_kwh, 2)
    # Overwrite Tibber total in totals with value from Tibber sensor, split into spot and markup
    tibber_abonnemang_ex_moms = cost_config.get("subscriptions", {}).get(
        "tibber_abonnemang_ex_moms", 39.20
    )
    spot_ex_moms = energy_total_spot / (1 + moms_rate)
    markup_ex_moms = energy_total_markup / (1 + moms_rate)
    tibber_el_cost_ex_moms = spot_ex_moms + markup_ex_moms
    tibber_subtotal_ex_moms = tibber_el_cost_ex_moms + tibber_abonnemang_ex_moms
    tibber_moms = tibber_subtotal_ex_moms * moms_rate
    tibber_total_inkl_moms = tibber_subtotal_ex_moms + tibber_moms
    totals["tibber"] = {
        "el_cost_ex_moms": round(tibber_el_cost_ex_moms, 2),
        "spot_ex_moms": round(spot_ex_moms, 2),
        "markup_ex_moms": round(markup_ex_moms, 2),
        "abonnemang_ex_moms": round(tibber_abonnemang_ex_moms, 2),
        "subtotal_ex_moms": round(tibber_subtotal_ex_moms, 2),
        "moms": round(tibber_moms, 2),
        "total_inkl_moms": round(tibber_total_inkl_moms, 2),
    }
    # Overwrite E.ON grid fees in totals to use Tibber sensor consumption
    utility_operator = cost_config.get("utility_operator", {})
    if (
        "overforingsavgift_per_kwh" not in utility_operator
        or "energiskatt_per_kwh" not in utility_operator
    ):
        raise ValueError(
            "Missing E.ON rates in config: overforingsavgift_per_kwh or energiskatt_per_kwh"
        )
    eon_overforingsavgift = (
        energy_total_kwh * utility_operator["overforingsavgift_per_kwh"]
    )
    eon_energiskatt = energy_total_kwh * utility_operator["energiskatt_per_kwh"]
    eon_abonnemang_ex_moms = utility_operator["abonnemang_ex_moms"]
    eon_subtotal_ex_moms = (
        eon_overforingsavgift + eon_energiskatt + eon_abonnemang_ex_moms
    )
    eon_moms = eon_subtotal_ex_moms * moms_rate
    eon_total_inkl_moms = eon_subtotal_ex_moms + eon_moms
    totals["eon"] = {
        "overforingsavgift_ex_moms": round(eon_overforingsavgift, 2),
        "energiskatt_ex_moms": round(eon_energiskatt, 2),
        "abonnemang_ex_moms": round(eon_abonnemang_ex_moms, 2),
        "subtotal_ex_moms": round(eon_subtotal_ex_moms, 2),
        "moms": round(eon_moms, 2),
        "total_inkl_moms": round(eon_total_inkl_moms, 2),
    }
    # Add per-area spot and markup for frontend
    totals["areas_spot_markup"] = {
        "gardshus": {
            "spot_ex_moms": round(gardshus_spot / (1 + moms_rate), 2),
            "markup_ex_moms": round(gardshus_markup / (1 + moms_rate), 2),
        },
        "salong": {
            "spot_ex_moms": round(salong_spot / (1 + moms_rate), 2),
            "markup_ex_moms": round(salong_markup / (1 + moms_rate), 2),
        },
    }

    # Build hourly data for the table
    hourly_data = []
    for idx, row in df.iterrows():
        # idx is a DatetimeIndex entry (Timestamp), but typed as Hashable
        timestamp: pd.Timestamp = idx  # type: ignore[assignment]
        hourly_data.append(
            {
                "time": timestamp.isoformat(),
                "gardshus_kwh": (
                    round(row["gardshus_consumption"], 2)
                    if not pd.isna(row["gardshus_consumption"])
                    else None
                ),
                "salong_kwh": (
                    round(row["salong_consumption"], 2)
                    if not pd.isna(row["salong_consumption"])
                    else None
                ),
                "price_sek": (
                    round(row["price"], 2) if not pd.isna(row["price"]) else None
                ),
                "gardshus_cost": (
                    round(row["gardshus_cost"], 2)
                    if not pd.isna(row["gardshus_cost"])
                    else None
                ),
                "salong_cost": (
                    round(row["salong_cost"], 2)
                    if not pd.isna(row["salong_cost"])
                    else None
                ),
                "estimated": bool(
                    gardshus_estimated.get(timestamp, False)
                    or salong_estimated.get(timestamp, False)
                ),
            }
        )

    # Get Tibber markup from config for UI
    tibber_markup_per_kwh_ex_moms = cost_config.get("energy_supplier", {}).get(
        "markup_per_kwh_ex_moms", 0.068
    )
    # Calculate average spot price in öre/kWh (ex moms)
    avg_spot_ore_per_kwh = (
        round(avg_spot_ex_moms * 100, 1) if avg_spot_ex_moms is not None else None
    )

    # Expose E.ON rates for frontend display
    eon_rates = {
        "overforingsavgift_per_kwh": cost_config.get("utility_operator", {}).get(
            "overforingsavgift_per_kwh"
        ),
        "energiskatt_per_kwh": cost_config.get("utility_operator", {}).get(
            "energiskatt_per_kwh"
        ),
        "abonnemang_ex_moms": cost_config.get("utility_operator", {}).get(
            "abonnemang_ex_moms"
        ),
    }
    return {
        "period": {
            "year": year,
            "month": month,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "hourly_data": hourly_data,
        "areas": {
            "gardshus": gardshus_invoice,
            "salong": salong_invoice,
        },
        "total": totals,
        "energy_sensor_kwh": round(energy_total_kwh, 2),
        "average_price_sek_kwh": (
            round(avg_spot_ex_moms, 4) if avg_spot_ex_moms is not None else None
        ),
        "tibber_markup_per_kwh_ex_moms": tibber_markup_per_kwh_ex_moms,
        "average_spot_ore_per_kwh": avg_spot_ore_per_kwh,
        "eon_rates": eon_rates,
    }


@router.get("/report/invoice")
async def get_invoice_report(
    start_year: int = Query(..., ge=2020, le=2100),
    start_month: int = Query(..., ge=1, le=12),
    end_year: int = Query(..., ge=2020, le=2100),
    end_month: int = Query(..., ge=1, le=12),
) -> dict:
    """
    Get invoice data for salong over a range of months.

    Returns per-month rows with meter reading, consumption, cost per kWh,
    and total cost, plus a grand total.
    """
    influx = get_influx_service()

    # Validate range
    start_val = start_year * 12 + start_month
    end_val = end_year * 12 + end_month
    if start_val > end_val:
        raise HTTPException(
            status_code=400, detail="Start month must be before or equal to end month"
        )
    if end_val - start_val > 24:
        raise HTTPException(
            status_code=400, detail="Range must not exceed 24 months"
        )

    logger.info(
        f"Generating invoice report for {start_year}-{start_month:02d} to {end_year}-{end_month:02d}"
    )

    # Get previous month's reading as baseline for first month's consumption
    prev_y = start_year if start_month > 1 else start_year - 1
    prev_m = start_month - 1 if start_month > 1 else 12
    baseline = _compute_month_data(prev_y, prev_m, influx)
    prev_reading = baseline["salong_meter_reading"] if baseline else None

    # Iterate through each month in range
    invoice_months: list[dict] = []
    y, m = start_year, start_month
    while y * 12 + m <= end_val:
        computed = _compute_month_data(y, m, influx)
        last_day = monthrange(y, m)[1]

        reading = computed["salong_meter_reading"] if computed else None
        salong_inv = computed["salong_invoice"] if computed else None

        if reading is not None and prev_reading is not None and salong_inv is not None:
            consumption = round(reading - prev_reading, 1)
            # Use the same total_inkl_moms as the monthly report
            total_cost = salong_inv["total_inkl_moms"]
            cost_per_kwh = round(total_cost / consumption, 2) if consumption > 0 else 0
        else:
            consumption = None
            total_cost = None
            cost_per_kwh = None

        invoice_months.append({
            "year": y,
            "month": m,
            "period_label": f"{MONTHS_SV[m - 1]} {y}",
            "period_start": f"{y}-{m:02d}-01",
            "period_end": f"{y}-{m:02d}-{last_day}",
            "meter_reading_kwh": reading,
            "consumption_kwh": consumption,
            "cost_per_kwh": cost_per_kwh,
            "total_cost_sek": total_cost,
        })

        prev_reading = reading
        # Advance to next month
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1

    # Calculate grand totals
    total_consumption = sum(
        row["consumption_kwh"] for row in invoice_months if row["consumption_kwh"] is not None
    )
    total_cost = sum(
        row["total_cost_sek"] for row in invoice_months if row["total_cost_sek"] is not None
    )

    return {
        "invoice_months": invoice_months,
        "grand_total": {
            "total_consumption_kwh": round(total_consumption, 1),
            "total_cost_sek": round(total_cost, 2),
        },
    }
