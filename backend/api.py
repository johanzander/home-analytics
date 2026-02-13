"""
API Router for Home Analytics Add-on

Exposes endpoints to query energy data.
"""

import asyncio
import json
from calendar import monthrange
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response
from loguru import logger
from services.influx_service import InfluxService


# ---------------------------------------------------------------------------
# Area definitions: maps area key → list of sensor config keys
# For single-sensor areas, consumption = diff(sensor)
# For composite areas (varmepump), consumption = sum of diffs
# ---------------------------------------------------------------------------
AREA_DEFINITIONS = {
    "gardshus": {"sensor_keys": ["gardshus"], "needs_cleaning": False},
    "salong": {"sensor_keys": ["salong"], "needs_cleaning": False},
    "billaddning": {"sensor_keys": ["billaddning"], "needs_cleaning": False},
    "varmepump": {"sensor_keys": ["varmepump_kompressor", "varmepump_tilsats"], "needs_cleaning": True},
}

# Canonical order for frontend display
AREA_ORDER = ["gardshus", "salong", "billaddning", "varmepump", "ovrigt"]


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
        "billaddning": options["sensors"].get("billaddning", ""),
        "varmepump_kompressor": options["sensors"].get("varmepump_kompressor", ""),
        "varmepump_tilsats": options["sensors"].get("varmepump_tilsats", ""),
        "electricity_price": options["sensors"].get("electricity_price", ""),
        "energy_consumption": options["sensors"].get("energy_consumption", ""),
    }


def load_cost_config() -> dict[str, Any]:
    """Load cost rates from options hierarchy."""
    cost_opts = options.get("cost", {})
    areas_opts = cost_opts.get("areas", {})

    # Build areas config dynamically from AREA_DEFINITIONS
    areas = {}
    for area_key in AREA_DEFINITIONS:
        area_cfg = areas_opts.get(area_key, {})
        areas[area_key] = {
            "name": area_cfg.get("name", area_key.capitalize()),
            "eon_abonnemang_bidrag_inkl_moms": area_cfg.get(
                "eon_abonnemang_bidrag_inkl_moms", 0
            ),
        }

    energy_supplier_opts = cost_opts.get("energy_supplier", {})
    utility_operator_opts = cost_opts.get("utility_operator", {})
    common_opts = cost_opts.get("common", {})

    return {
        "areas": areas,
        "energy_supplier": {
            "abonnemang_ex_moms": energy_supplier_opts.get(
                "abonnemang_ex_moms",
                options.get("tibber_subscription_ex_moms", 39.20),
            ),
            "markup_per_kwh_ex_moms": energy_supplier_opts.get(
                "markup_per_kwh_ex_moms",
                options.get("tibber_markup_per_kwh_ex_moms", 0.068),
            ),
        },
        "utility_operator": {
            "overforingsavgift_per_kwh": utility_operator_opts.get(
                "overforingsavgift_per_kwh",
                options.get("eon_transfer_fee_per_kwh", 0.2456),
            ),
            "energiskatt_per_kwh": utility_operator_opts.get(
                "energiskatt_per_kwh",
                options.get("eon_energy_tax_per_kwh", 0.439),
            ),
            "abonnemang_ex_moms": utility_operator_opts.get(
                "abonnemang_ex_moms",
                options.get("eon_subscription_ex_moms", 805.00),
            ),
        },
        "common": {
            "moms_rate": common_opts.get(
                "moms_rate",
                options.get("vat_rate", 0.25),
            ),
        },
    }


def calculate_area_invoice(
    consumption_kwh: float,
    hourly_tibber_cost: float,
    area_key: str,
    cost_config: dict,
) -> dict:
    """
    Calculate invoice for a single area.

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


def calculate_totals(area_invoices: dict[str, dict], cost_config: dict) -> dict:
    """
    Calculate total invoice (full electricity bill).

    Totals include full subscription fees (not split per area).
    """
    energy_supplier = cost_config.get("energy_supplier", {})
    utility_operator = cost_config.get("utility_operator", {})
    moms_rate = cost_config.get("common", {}).get("moms_rate", 0.25)

    # Total consumption (will be overwritten by Tibber sensor in main function)
    total_consumption = sum(inv["consumption_kwh"] for inv in area_invoices.values())

    # === TIBBER TOTAL ===
    # Sum of electricity costs + full Tibber subscription
    tibber_el_cost_ex_moms = sum(
        inv["tibber"]["el_cost_ex_moms"] for inv in area_invoices.values()
    )
    tibber_abonnemang_ex_moms = energy_supplier.get("abonnemang_ex_moms", 39.20)
    tibber_subtotal_ex_moms = tibber_el_cost_ex_moms + tibber_abonnemang_ex_moms
    tibber_moms = tibber_subtotal_ex_moms * moms_rate
    energy_consumption_inkl_moms = tibber_subtotal_ex_moms + tibber_moms

    # === E.ON TOTAL ===
    # Sum of grid fees + full E.ON subscription
    eon_overforingsavgift = sum(
        inv["eon"]["overforingsavgift_ex_moms"] for inv in area_invoices.values()
    )
    eon_energiskatt = sum(
        inv["eon"]["energiskatt_ex_moms"] for inv in area_invoices.values()
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


def _remove_outliers(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Auto-detect and remove outlier values from cumulative sensor columns.

    For cumulative meters the highest sustained cluster of values is always
    the real one (cumulative readings only go up).  Two detection modes:

    **Bimodal** (max > 10 × median) — the sensor alternates between a real
    high cluster and garbage low values (e.g. aux_consumption_tot reporting
    ~11 600 interspersed with ~927).  Values below 50 % of max are garbage.

    **Unimodal** (normal) — classic outlier removal: values below 1 % of
    median or above 200 % are flagged.

    After absolute cleaning a second pass catches **rate-of-change outliers**
    — hour-to-hour jumps exceeding 20× the typical hourly consumption.
    """
    for col in columns:
        if col not in df.columns:
            continue

        valid = df[col].dropna()
        if valid.empty:
            continue
        median_val = valid.median()
        max_val = valid.max()

        if pd.isna(median_val) or median_val <= 0:
            continue

        # --- Pass 1: absolute value outliers ---
        if max_val > median_val * 10 and max_val > 1000:
            # Bimodal: high cluster is real, low values are garbage
            lower = max_val * 0.5
            upper = max_val * 1.5
            abs_outliers = ((df[col] < lower) | (df[col] > upper)) & df[col].notna()
            if abs_outliers.any():
                logger.debug(
                    f"Sensor {col}: bimodal detected (max={max_val:.0f}, "
                    f"median={median_val:.0f}). {abs_outliers.sum()} values "
                    f"outside [{lower:.0f}, {upper:.0f}] → NaN"
                )
                df.loc[abs_outliers, col] = pd.NA
        elif median_val > 100:
            # Unimodal: standard median-based bounds
            lower = median_val * 0.01
            upper = median_val * 2.0
            abs_outliers = ((df[col] < lower) | (df[col] > upper)) & df[col].notna()
            if abs_outliers.any():
                logger.debug(
                    f"Sensor {col}: {abs_outliers.sum()} outliers outside "
                    f"[{lower:.0f}, {upper:.0f}] (median={median_val:.0f}) → NaN"
                )
                df.loc[abs_outliers, col] = pd.NA

        # --- Pass 2: rate-of-change outliers ---
        diffs = df[col].diff()
        pos_diffs = diffs[diffs > 0]
        if pos_diffs.empty:
            continue
        median_diff = pos_diffs.median()
        if pd.isna(median_diff) or median_diff <= 0:
            continue
        # Threshold: 20× the typical hourly consumption, at least 50 kWh
        threshold = max(median_diff * 20, 50)
        rate_outliers = (diffs > threshold) & diffs.notna()
        if rate_outliers.any():
            logger.debug(
                f"Sensor {col}: {rate_outliers.sum()} rate-of-change outliers "
                f"(diff > {threshold:.1f}, median_diff={median_diff:.2f}) → NaN"
            )
            df.loc[rate_outliers, col] = pd.NA

    return df


def _enforce_monotonicity(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Ensure cumulative meter columns are monotonically non-decreasing.

    If a value is lower than the previous row, replace it with the previous value.
    Mirrors reference/misc/fluxQueryServer.py lines 328-335.
    """
    for col in columns:
        if col not in df.columns:
            continue
        diffs = df[col].diff()
        negative = diffs < 0
        if negative.any():
            logger.debug(
                f"Fixing {negative.sum()} decreasing values in {col}"
            )
            # Replace the decreased value with the previous row's value
            df.loc[negative, col] = df[col].shift(1).loc[negative]
    return df


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

    # Query extra hours before the month for two reasons:
    #   1. diff() at 00:00 needs a previous value to subtract from
    #   2. Infrequent sensors (e.g. billaddning) need a wider window so
    #      their first/last non-NaN boundary (used for estimated flags)
    #      doesn't falsely mark early hours as estimated.
    from datetime import timedelta
    query_start = start_date - timedelta(hours=48)

    sensors = load_sensors_config()
    sensor_list = [s for s in sensors.values() if s]
    df = influx.query_specific_sensors(
        start_date=query_start, end_date=end_date, sensor_list=sensor_list
    )

    if df.empty:
        if not is_current_month:
            _month_cache[key] = {"data": None, "cached_at": datetime.now()}
        return None

    # Determine which areas have data (all sensor keys present in df)
    area_has_data: dict[str, bool] = {}
    for area_key, area_def in AREA_DEFINITIONS.items():
        area_has_data[area_key] = all(
            sensors[sk] and sensors[sk] in df.columns
            for sk in area_def["sensor_keys"]
        )

    # Need at least one area with data
    if not any(area_has_data.values()):
        if not is_current_month:
            _month_cache[key] = {"data": None, "cached_at": datetime.now()}
        return None

    # Collect all sensor entity IDs used by areas that have data
    all_area_sensor_ids = []
    for area_key, area_def in AREA_DEFINITIONS.items():
        if area_has_data[area_key]:
            for sk in area_def["sensor_keys"]:
                all_area_sensor_ids.append(sensors[sk])

    # --- Data quality pipeline ---
    #
    # The data arrives from influx_service WITHOUT forward-fill so we can
    # distinguish "no data captured" (NaN) from "cumulative reading unchanged."
    #
    # Pipeline order:
    #   1. Track estimated (hours beyond sensor's last real data point)
    #   2. Forward-fill (correct for cumulative meters between data points)
    #   3. Outlier removal (detect garbage values)
    #   4. Interpolate remaining gaps (from outlier removal)
    #   5. Enforce monotonicity

    # Step 1: Track estimated — for each sensor, find the last timestamp
    # with real data.  Hours after that are "estimated" (no data captured,
    # e.g. future hours in the current month or sensor offline).
    # We do this BEFORE ffill because ffill would mask the boundary.
    area_estimated: dict[str, pd.Series] = {}
    for area_key, area_def in AREA_DEFINITIONS.items():
        if not area_has_data[area_key]:
            area_estimated[area_key] = pd.Series(dtype=bool)
            continue
        estimated = pd.Series(False, index=df.index)
        for sk in area_def["sensor_keys"]:
            sensor_id = sensors[sk]
            if sensor_id in df.columns:
                # Find first and last non-NaN value for this sensor
                valid_mask = df[sensor_id].notna()
                if valid_mask.any():
                    first_valid = df.index[valid_mask][0]
                    last_valid = df.index[valid_mask][-1]
                    # Before first or after last real data point → estimated
                    estimated = estimated | (df.index < first_valid) | (df.index > last_valid)
                else:
                    # No data at all — everything is estimated
                    estimated = estimated | True
        area_estimated[area_key] = estimated

    # Step 2: Forward-fill cumulative meter readings.
    # Fills gaps between reports (correct for cumulative meters).
    for sensor_id in all_area_sensor_ids:
        if sensor_id in df.columns:
            df[sensor_id] = df[sensor_id].ffill()

    # Also ffill the total energy and price sensors (non-area but cumulative/continuous).
    # Without this, iloc[-1] returns NaN for current month (future hours have no data).
    for extra_key in ("energy_consumption", "electricity_price"):
        sid = sensors.get(extra_key, "")
        if sid and sid in df.columns:
            df[sid] = df[sid].ffill()

    # Post-ffill validation for composite areas: if a sensor is still
    # all-NaN after ffill (no data at all), downgrade the area.
    for area_key, area_def in AREA_DEFINITIONS.items():
        if not area_has_data[area_key] or len(area_def["sensor_keys"]) <= 1:
            continue
        for sk in area_def["sensor_keys"]:
            sensor_id = sensors[sk]
            if sensor_id in df.columns and df[sensor_id].isna().all():
                logger.warning(
                    f"Composite area {area_key}: sensor {sk} has no data after ffill, disabling area"
                )
                area_has_data[area_key] = False
                break

    # Step 3: Auto-detect outliers (garbage values, spikes).
    # Only run on sensors flagged with needs_cleaning (e.g. varmepump).
    # Clean sensors like gardshus, salong, billaddning don't need this.
    cleanable_sensor_ids = []
    for area_key, area_def in AREA_DEFINITIONS.items():
        if area_has_data[area_key] and area_def.get("needs_cleaning"):
            for sk in area_def["sensor_keys"]:
                cleanable_sensor_ids.append(sensors[sk])

    # Track NaN counts before/after to compute data quality per area.
    pre_outlier_nans = {
        sid: int(df[sid].isna().sum()) for sid in cleanable_sensor_ids if sid in df.columns
    }
    df = _remove_outliers(df, cleanable_sensor_ids)
    post_outlier_nans = {
        sid: int(df[sid].isna().sum()) for sid in cleanable_sensor_ids if sid in df.columns
    }

    # Per-area data quality: percentage of hourly rows not affected by cleaning.
    # Use n_rows (not n_rows × n_sensors) so composite areas aren't diluted.
    n_rows = len(df)
    area_data_quality: dict[str, float] = {}
    for area_key, area_def in AREA_DEFINITIONS.items():
        if not area_has_data[area_key]:
            continue
        total_cleaned = 0
        for sk in area_def["sensor_keys"]:
            sensor_id = sensors[sk]
            if sensor_id in df.columns:
                total_cleaned += post_outlier_nans.get(sensor_id, 0) - pre_outlier_nans.get(sensor_id, 0)
        if n_rows > 0:
            area_data_quality[area_key] = round(1.0 - total_cleaned / n_rows, 3)
        else:
            area_data_quality[area_key] = 1.0

    # Step 4: Interpolate / forward-fill / backward-fill remaining gaps
    # (from outlier removal).  No rounding — fractional values from
    # interpolation serve as a visible signal that data was cleaned.
    for sensor_id in all_area_sensor_ids:
        if sensor_id in df.columns:
            df[sensor_id] = (
                df[sensor_id].interpolate(method="linear").ffill().bfill()
            )

    # Step 5: Enforce monotonicity — cumulative meters should never decrease
    df = _enforce_monotonicity(df, all_area_sensor_ids)

    # Save sensor baselines (value at hour before month start) for normalization.
    # After computing hourly diffs, the sum can diverge from the meter reading
    # difference due to data quality (spikes, monotonicity gaps).  We normalize
    # so hourly consumption adds up to the authoritative meter total.
    baseline_ts = start_date - timedelta(hours=1)
    area_sensor_baseline: dict[str, float] = {}
    for area_key, area_def in AREA_DEFINITIONS.items():
        if area_has_data[area_key] and len(area_def["sensor_keys"]) == 1:
            sensor_id = sensors[area_def["sensor_keys"][0]]
            if sensor_id in df.columns and baseline_ts in df.index:
                val = df.loc[baseline_ts, sensor_id]
                if pd.notna(val):
                    area_sensor_baseline[area_key] = float(val)

    # Calculate hourly consumption per area
    # Cumulative meters should never decrease, so clip negative diffs to 0.
    # Without this, data noise (e.g. from zero-replacement + interpolation)
    # can create +/- swings that cancel in the sum but explode when
    # multiplied by varying hourly prices.
    for area_key, area_def in AREA_DEFINITIONS.items():
        if not area_has_data[area_key]:
            continue
        if len(area_def["sensor_keys"]) == 1:
            sensor_id = sensors[area_def["sensor_keys"][0]]
            df[f"{area_key}_consumption"] = df[sensor_id].diff().clip(lower=0)
        else:
            # Composite area: sum clipped diffs from each sensor
            df[f"{area_key}_consumption"] = sum(
                df[sensors[sk]].diff().clip(lower=0) for sk in area_def["sensor_keys"]
            )

    # Get electricity price (already in SEK/kWh inkl moms)
    df["price"] = df[sensors["electricity_price"]] if sensors["electricity_price"] in df.columns else 0

    # Load cost configuration
    cost_config = load_cost_config()
    moms_rate = cost_config.get("common", {}).get("moms_rate", 0.25)
    tibber_markup_per_kwh_ex_moms = cost_config.get("energy_supplier", {}).get(
        "markup_per_kwh_ex_moms", 0.068
    )

    # Calculate spot, markup, cost for each area
    for area_key in AREA_DEFINITIONS:
        if f"{area_key}_consumption" not in df.columns:
            continue
        df[f"{area_key}_spot"] = df[f"{area_key}_consumption"] * (
            df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df[f"{area_key}_markup"] = (
            df[f"{area_key}_consumption"] * tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df[f"{area_key}_cost"] = df[f"{area_key}_spot"] + df[f"{area_key}_markup"]

    # Compute "övrigt" (uncategorized) = total energy consumption - sum of area consumptions.
    # Must happen BEFORE the trim so that diff() at 00:00 has a previous row.
    energy_sensor_id = sensors.get("energy_consumption", "")
    if energy_sensor_id and energy_sensor_id in df.columns:
        energy_diffs = df[energy_sensor_id].diff().clip(lower=0)
        area_sum = sum(
            df[f"{area_key}_consumption"]
            for area_key in AREA_DEFINITIONS
            if f"{area_key}_consumption" in df.columns
        )
        df["ovrigt_consumption"] = (energy_diffs - area_sum).clip(lower=0)
        df["ovrigt_spot"] = df["ovrigt_consumption"] * (
            df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df["ovrigt_markup"] = (
            df["ovrigt_consumption"] * tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df["ovrigt_cost"] = df["ovrigt_spot"] + df["ovrigt_markup"]
        area_has_data["ovrigt"] = True
    else:
        area_has_data["ovrigt"] = False

    # Trim the extra pre-month hours now that all diffs have been computed.
    # Also trim area_estimated to match.
    df = df.loc[start_date:]
    for area_key in area_estimated:
        if not area_estimated[area_key].empty:
            area_estimated[area_key] = area_estimated[area_key].loc[start_date:]

    # For the current month, truncate to the current hour so we don't show
    # hundreds of future estimated rows in the hourly table.
    if is_current_month:
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        df = df.loc[:current_hour]
        for area_key in area_estimated:
            if not area_estimated[area_key].empty:
                area_estimated[area_key] = area_estimated[area_key].loc[:current_hour]

    # Extract meter readings from the final (trimmed) df.
    area_meter_readings: dict[str, float | None] = {}
    for area_key, area_def in AREA_DEFINITIONS.items():
        if area_has_data[area_key] and len(area_def["sensor_keys"]) == 1:
            sensor_id = sensors[area_def["sensor_keys"][0]]
            area_meter_readings[area_key] = round(float(df[sensor_id].iloc[-1]), 1)
        else:
            area_meter_readings[area_key] = None

    # Normalize hourly consumption so it adds up to the meter reading total.
    # Data quality issues (spikes surviving single-pass monotonicity + clip)
    # can cause hourly diff sums to diverge from the authoritative meter.
    for area_key, baseline_val in area_sensor_baseline.items():
        cons_col = f"{area_key}_consumption"
        if cons_col not in df.columns:
            continue
        sensor_id = sensors[AREA_DEFINITIONS[area_key]["sensor_keys"][0]]
        end_val = float(df[sensor_id].iloc[-1])
        meter_diff = end_val - baseline_val
        hourly_sum = df[cons_col].sum()
        if hourly_sum > 0 and meter_diff > 0 and abs(hourly_sum - meter_diff) > 0.5:
            scale = meter_diff / hourly_sum
            for col in (cons_col, f"{area_key}_spot", f"{area_key}_markup", f"{area_key}_cost"):
                if col in df.columns:
                    df[col] *= scale
            logger.debug(
                f"Normalized {area_key}: {hourly_sum:.1f} → {meter_diff:.1f} kWh (×{scale:.4f})"
            )

    # Recompute övrigt after normalization
    if area_has_data.get("ovrigt"):
        energy_diffs_trimmed = df[energy_sensor_id].diff().clip(lower=0)
        # First hour's diff is NaN after trim — use the pre-computed value
        if pd.isna(energy_diffs_trimmed.iloc[0]) and "ovrigt_consumption" in df.columns:
            energy_diffs_trimmed.iloc[0] = df["ovrigt_consumption"].iloc[0] + sum(
                df[f"{ak}_consumption"].iloc[0]
                for ak in AREA_DEFINITIONS
                if f"{ak}_consumption" in df.columns
            )
        area_sum = sum(
            df[f"{ak}_consumption"]
            for ak in AREA_DEFINITIONS
            if f"{ak}_consumption" in df.columns
        )
        df["ovrigt_consumption"] = (energy_diffs_trimmed - area_sum).clip(lower=0)
        df["ovrigt_spot"] = df["ovrigt_consumption"] * (
            df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df["ovrigt_markup"] = (
            df["ovrigt_consumption"] * tibber_markup_per_kwh_ex_moms * (1 + moms_rate)
        )
        df["ovrigt_cost"] = df["ovrigt_spot"] + df["ovrigt_markup"]
        area_estimated["ovrigt"] = pd.Series(False, index=df.index)

    # Calculate per-area invoices (using normalized data)
    area_invoices: dict[str, dict] = {}
    for area_key in AREA_DEFINITIONS:
        if not area_has_data[area_key]:
            continue
        area_kwh = float(df[f"{area_key}_consumption"].sum())
        area_el_cost = float(df[f"{area_key}_cost"].sum())
        area_invoices[area_key] = calculate_area_invoice(
            consumption_kwh=area_kwh,
            hourly_tibber_cost=area_el_cost,
            area_key=area_key,
            cost_config=cost_config,
        )

    # Add övrigt to invoices
    if area_has_data.get("ovrigt"):
        ovrigt_kwh = float(df["ovrigt_consumption"].sum())
        ovrigt_el_cost = float(df["ovrigt_cost"].sum())
        area_invoices["ovrigt"] = calculate_area_invoice(
            consumption_kwh=ovrigt_kwh,
            hourly_tibber_cost=ovrigt_el_cost,
            area_key="ovrigt",
            cost_config=cost_config,
        )

    result = {
        "start_date": start_date,
        "end_date": end_date,
        "is_current_month": is_current_month,
        "df": df,
        "sensors": sensors,
        "cost_config": cost_config,
        "area_invoices": area_invoices,
        "area_meter_readings": area_meter_readings,
        "area_estimated": area_estimated,
        "area_has_data": area_has_data,
        "area_data_quality": area_data_quality,
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
    return {"message": "Hello from API!", "version": "0.2.0"}


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
    Get monthly energy consumption and cost report.

    Returns consumption in kWh and cost in SEK for the specified month,
    broken down by area (gardshus, salong, billaddning, varmepump).
    """
    logger.info(f"Generating monthly report for {year}-{month:02d}")

    # Use shared monthly computation
    computed = _compute_month_data(year, month, get_influx_service())
    if computed is None:
        raise HTTPException(status_code=404, detail="No data available for this period")

    df = computed["df"]
    sensors = computed["sensors"]
    cost_config = computed["cost_config"]
    area_invoices = computed["area_invoices"]
    area_estimated = computed["area_estimated"]
    area_has_data = computed["area_has_data"]
    area_data_quality = computed["area_data_quality"]
    start_date = computed["start_date"]
    end_date = computed["end_date"]
    is_current_month = computed["is_current_month"]

    # Check that price and total consumption sensors are present
    required_sensors = ["electricity_price", "energy_consumption"]
    missing = [name for name in required_sensors if sensors[name] not in df.columns]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Missing sensors in data: {missing}. Available: {list(df.columns)}",
        )

    if not area_invoices:
        raise HTTPException(status_code=404, detail="No area data available for report")

    moms_rate = cost_config.get("common", {}).get("moms_rate", 0.25)
    tibber_markup_per_kwh_ex_moms = cost_config.get("energy_supplier", {}).get(
        "markup_per_kwh_ex_moms", 0.068
    )

    # Build areas_spot_markup for all areas with data
    areas_spot_markup = {}
    for area_key in area_invoices:
        if f"{area_key}_spot" in df.columns:
            area_spot = float(df[f"{area_key}_spot"].sum())
            area_markup = float(df[f"{area_key}_markup"].sum())
            areas_spot_markup[area_key] = {
                "spot_ex_moms": round(area_spot / (1 + moms_rate), 2),
                "markup_ex_moms": round(area_markup / (1 + moms_rate), 2),
            }

    # Calculate Tibber total for the property (from Tibber sensor)
    energy_first = df[sensors["energy_consumption"]].iloc[0]
    energy_last = df[sensors["energy_consumption"]].iloc[-1]
    energy_total_kwh = energy_last - energy_first
    energy_diffs = df[sensors["energy_consumption"]].diff().clip(lower=0)
    energy_total_spot = (
        (df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate))
        * energy_diffs
    ).sum()
    energy_total_markup = (
        energy_diffs
        * tibber_markup_per_kwh_ex_moms
        * (1 + moms_rate)
    ).sum()

    # Calculate average spot price (ex moms) based on Tibber sensor
    valid = energy_diffs > 0
    spot_per_hour = (df["price"] - tibber_markup_per_kwh_ex_moms * (1 + moms_rate)) / (
        1 + moms_rate
    )
    weighted_spot_sum = (spot_per_hour[valid] * energy_diffs[valid]).sum()
    total_kwh = energy_diffs[valid].sum()
    avg_spot_ex_moms = weighted_spot_sum / total_kwh if total_kwh > 0 else None

    # Calculate totals (includes full subscription fees)
    totals = calculate_totals(area_invoices, cost_config)
    totals["consumption_kwh"] = round(energy_total_kwh, 2)

    # Overwrite Tibber total with value from Tibber sensor, split into spot and markup
    tibber_abonnemang_ex_moms = cost_config.get("energy_supplier", {}).get(
        "abonnemang_ex_moms", 39.20
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
    totals["areas_spot_markup"] = areas_spot_markup

    # Build hourly data with dynamic area columns
    active_areas = [a for a in AREA_ORDER if area_has_data.get(a)]
    hourly_data = []
    for idx, row in df.iterrows():
        timestamp: pd.Timestamp = idx  # type: ignore[assignment]
        entry: dict[str, Any] = {
            "time": timestamp.isoformat(),
            "price_sek": (
                round(row["price"], 2) if not pd.isna(row["price"]) else None
            ),
        }
        for area_key in active_areas:
            cons_col = f"{area_key}_consumption"
            cost_col = f"{area_key}_cost"
            entry[f"{area_key}_kwh"] = (
                round(row[cons_col], 2)
                if cons_col in df.columns and not pd.isna(row[cons_col])
                else None
            )
            entry[f"{area_key}_cost"] = (
                round(row[cost_col], 2)
                if cost_col in df.columns and not pd.isna(row[cost_col])
                else None
            )
        # Per-area estimated flags: only mark the specific areas that
        # had NaN sensor data (before interpolation) for this hour.
        est_areas = [
            area_key for area_key in active_areas
            if area_estimated.get(area_key, pd.Series(dtype=bool)).get(timestamp, False)
        ]
        entry["estimated"] = len(est_areas) > 0
        entry["estimated_areas"] = est_areas
        hourly_data.append(entry)

    # Get area names from cost config for frontend
    _area_name_defaults = {"ovrigt": "Övrigt"}
    area_names = {}
    for area_key in AREA_ORDER:
        area_cfg = cost_config.get("areas", {}).get(area_key, {})
        area_names[area_key] = area_cfg.get(
            "name", _area_name_defaults.get(area_key, area_key.capitalize())
        )

    # Calculate average spot price in öre/kWh (ex moms)
    avg_spot_ore_per_kwh = (
        round(avg_spot_ex_moms * 100, 1) if avg_spot_ex_moms is not None else None
    )

    # Expose E.ON rates for frontend display
    eon_rates = {
        "overforingsavgift_per_kwh": utility_operator.get("overforingsavgift_per_kwh"),
        "energiskatt_per_kwh": utility_operator.get("energiskatt_per_kwh"),
        "abonnemang_ex_moms": utility_operator.get("abonnemang_ex_moms"),
    }
    return {
        "period": {
            "year": year,
            "month": month,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "is_current_month": is_current_month,
        "hourly_data": hourly_data,
        "areas": area_invoices,
        "area_order": [a for a in AREA_ORDER if a in area_invoices],
        "area_names": area_names,
        "total": totals,
        "energy_sensor_kwh": round(energy_total_kwh, 2),
        "average_price_sek_kwh": (
            round(avg_spot_ex_moms, 4) if avg_spot_ex_moms is not None else None
        ),
        "tibber_markup_per_kwh_ex_moms": tibber_markup_per_kwh_ex_moms,
        "average_spot_ore_per_kwh": avg_spot_ore_per_kwh,
        "eon_rates": eon_rates,
        "area_data_quality": area_data_quality,
    }


@router.get("/report/invoice")
async def get_invoice_report(
    start_year: int = Query(..., ge=2020, le=2100),
    start_month: int = Query(..., ge=1, le=12),
    end_year: int = Query(..., ge=2020, le=2100),
    end_month: int = Query(..., ge=1, le=12),
    area: str = Query("salong", description="Area key (e.g. salong, gardshus)"),
) -> dict:
    """
    Get invoice data for a single-sensor area over a range of months.

    Returns per-month rows with meter reading, consumption, cost per kWh,
    and total cost, plus a grand total.
    """
    # Validate area
    if area not in AREA_DEFINITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown area '{area}'. Available: {list(AREA_DEFINITIONS.keys())}",
        )
    area_def = AREA_DEFINITIONS[area]
    if len(area_def["sensor_keys"]) != 1:
        raise HTTPException(
            status_code=400,
            detail=f"Area '{area}' is a composite area and cannot be used for invoice (no single meter reading).",
        )

    influx = get_influx_service()
    cost_config = load_cost_config()
    area_cfg = cost_config.get("areas", {}).get(area, {})
    area_name = area_cfg.get("name", area.capitalize())
    eon_abonnemang_inkl_moms = area_cfg.get("eon_abonnemang_bidrag_inkl_moms", 0)
    has_eon_abonnemang = eon_abonnemang_inkl_moms > 0
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
        f"Generating invoice report ({area}) for {start_year}-{start_month:02d} to {end_year}-{end_month:02d}"
    )

    # Get previous month's reading as baseline for first month's consumption
    prev_y = start_year if start_month > 1 else start_year - 1
    prev_m = start_month - 1 if start_month > 1 else 12
    baseline = _compute_month_data(prev_y, prev_m, influx)
    prev_reading = baseline["area_meter_readings"].get(area) if baseline else None

    # Iterate through each month in range
    invoice_months: list[dict] = []
    y, m = start_year, start_month
    while y * 12 + m <= end_val:
        computed = _compute_month_data(y, m, influx)
        last_day = monthrange(y, m)[1]

        reading = computed["area_meter_readings"].get(area) if computed else None
        area_inv = computed["area_invoices"].get(area) if computed else None

        if reading is not None and prev_reading is not None and area_inv is not None:
            consumption = round(reading - prev_reading, 1)
            # Data is already normalized in _compute_month_data so hourly
            # consumption adds up to the meter total. Just use the invoice directly.
            total_cost = area_inv["total_inkl_moms"]
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
            "eon_abonnemang_sek": round(eon_abonnemang_inkl_moms, 2) if has_eon_abonnemang and consumption else None,
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
    total_eon_abon = sum(
        row["eon_abonnemang_sek"] for row in invoice_months if row["eon_abonnemang_sek"] is not None
    )

    return {
        "area_key": area,
        "area_name": area_name,
        "has_eon_abonnemang": has_eon_abonnemang,
        "eon_abonnemang_inkl_moms": round(eon_abonnemang_inkl_moms, 2),
        "invoice_months": invoice_months,
        "grand_total": {
            "total_consumption_kwh": round(total_consumption, 1),
            "total_cost_sek": round(total_cost, 2),
            "total_eon_abonnemang_sek": round(total_eon_abon, 2) if has_eon_abonnemang else None,
        },
    }


# ---------------------------------------------------------------------------
# Invoice settings persistence
# ---------------------------------------------------------------------------

_invoice_settings_lock = asyncio.Lock()


def _get_settings_path() -> Path:
    """Return path for invoice settings JSON file."""
    prod_path = Path("/data/invoice_settings.json")
    if prod_path.parent.exists():
        return prod_path
    return Path(__file__).parent.parent / "data" / "invoice_settings.json"


@router.get("/invoice/settings")
async def get_invoice_settings() -> dict:
    settings_path = _get_settings_path()
    if settings_path.exists():
        with open(settings_path) as f:
            return json.load(f)
    return {
        "recipient": {"company": "", "street": "", "postal_city": "", "org_number": ""},
        "sender": {"name": "", "street": "", "postal_city": "", "phone": "", "email": ""},
        "next_invoice_number": 1,
        "bank_account": "",
        "due_days": 15,
    }


@router.post("/invoice/settings")
async def save_invoice_settings(settings: dict) -> dict:
    settings_path = _get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    return {"status": "ok"}


@router.post("/invoice/settings/increment-number")
async def increment_invoice_number() -> dict:
    async with _invoice_settings_lock:
        settings_path = _get_settings_path()
        settings = {}
        if settings_path.exists():
            with open(settings_path) as f:
                settings = json.load(f)
        current = settings.get("next_invoice_number", 2501)
        settings["next_invoice_number"] = current + 1
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    return {"used_number": current}
