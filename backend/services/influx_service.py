"""
InfluxDB Service for HomeAnalytics

Queries energy data from InfluxDB using individual sensor queries,
then merges results in pandas. This approach is more reliable than
trying to pivot multiple sensors in a single Flux query.

Based on patterns from reference/misc/fluxQueryServer.py
"""

import io
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import pytz
import requests
from dotenv import load_dotenv
from loguru import logger


class InfluxService:
    """Service to interact with InfluxDB."""

    influx_url: str
    influx_username: str
    influx_password: str

    def __init__(self, options: dict[str, Any]) -> None:
        """Initialize the InfluxService. Always load credentials from .env in dev, matching BESS hierarchy."""
        import os

        dev_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
        if dev_mode:
            load_dotenv()
            url = os.getenv("HA_DB_URL", "")
            username = os.getenv("HA_DB_USER_NAME", "")
            password = os.getenv("HA_DB_PASSWORD", "")
            bucket = os.getenv(
                "HA_DB_BUCKET",
                os.getenv("INFLUXDB_BUCKET_NAME", ""),
            )
            logger.debug(
                f"InfluxService DEV: url={url}, username={username}, password={'***' if password else ''}, bucket={bucket}, from_env=True"
            )
        else:
            influx = options.get("influx", {})
            url = influx.get("url", "")
            username = influx.get("username", "")
            password = influx.get("password", "")
            bucket = influx.get("bucket", "home_assistant/autogen")
            logger.debug(
                f"InfluxService PROD: url={url}, username={username}, password={'***' if password else ''}, bucket={bucket}, from_env=False"
            )

        if not url or not username or not password:
            raise ValueError(
                "InfluxDB connection details (url, username, password) not found in .env (dev) or options hierarchy (prod)."
            )

        self.influx_url = url
        self.influx_username = username
        self.influx_password = password
        self.bucket = bucket

        self.auth = requests.auth.HTTPBasicAuth(
            self.influx_username, self.influx_password
        )
        self.headers = {
            "Content-type": "application/vnd.flux",
            "Accept": "application/csv",
        }
        self.local_tz = pytz.timezone("Europe/Stockholm")
        self.sensors = self._load_sensors(options)

    @staticmethod
    def _load_sensors(options: dict[str, Any]) -> list[str]:
        """Load the list of sensors from options hierarchy."""
        sensors_cfg = options.get("sensors", {})
        sensors = [
            sensors_cfg.get("gardshus", ""),
            sensors_cfg.get("salong", ""),
            sensors_cfg.get("electricity_price", ""),
            sensors_cfg.get("energy_consumption", ""),
        ]
        return [s for s in sensors if s]  # Filter out empty strings

    def get_sensors(self) -> list[str]:
        """Return the list of loaded sensors."""
        return self.sensors

    def _to_utc_str(self, local_dt: datetime) -> str:
        """Convert local datetime to UTC string for Flux queries."""
        if local_dt.tzinfo is None:
            local_dt = self.local_tz.localize(local_dt)
        utc_dt = local_dt.astimezone(pytz.UTC)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _query_single_sensor(
        self, entity_id: str, start_utc: str, stop_utc: str
    ) -> pd.DataFrame:
        """
        Query a single sensor and return hourly data.

        Uses window(every: 1h) + first() to get the first value in each hour,
        which is appropriate for cumulative meter readings.
        """
        # Extract the entity_id without domain prefix if present
        # e.g., "sensor.outdoor" -> "outdoor"
        if "." in entity_id:
            domain, entity = entity_id.split(".", 1)
        else:
            domain = "sensor"
            entity = entity_id

        flux_query = f"""
from(bucket: "{self.bucket}")
    |> range(start: {start_utc}, stop: {stop_utc})
    |> filter(fn: (r) => r["entity_id"] == "{entity}")
    |> filter(fn: (r) => r["_field"] == "value")
    |> filter(fn: (r) => r["domain"] == "{domain}")
    |> window(every: 1h)
    |> first()
    |> duplicate(column: "_start", as: "_time")
    |> window(every: inf)
    |> drop(columns: ["result", "table", "_start", "_stop", "_field", "domain", "_measurement", "entity_id"])
"""

        logger.debug(f"Querying sensor: {entity_id}")

        try:
            response = requests.post(
                url=self.influx_url,
                auth=self.auth,
                headers=self.headers,
                data=flux_query,
                timeout=60,
            )

            if response.status_code != 200:
                logger.error(f"InfluxDB error for {entity_id}: {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                return pd.DataFrame()

            df = self._parse_csv_response(response.content.decode("utf-8"))

            if df.empty:
                logger.warning(f"No data returned for sensor: {entity_id}")
                return pd.DataFrame()

            # Rename _value column to entity_id
            if "_value" in df.columns:
                df = df.rename(columns={"_value": entity_id})
                df[entity_id] = pd.to_numeric(df[entity_id], errors="coerce")

            return df

        except Exception as e:
            logger.error(f"Error querying sensor {entity_id}: {e}")
            return pd.DataFrame()

    def _parse_csv_response(self, csv_data: str) -> pd.DataFrame:
        """
        Parse InfluxDB annotated CSV response.

        The response format has:
        - Row 0: #datatype header
        - Row 1: #group header
        - Row 2: #default header
        - Row 3: Column names
        - Row 4+: Data
        """
        if not csv_data.strip():
            return pd.DataFrame()

        lines = csv_data.strip().split("\n")

        # Need at least 5 lines (4 headers + 1 data)
        if len(lines) < 5:
            logger.warning("CSV response too short")
            return pd.DataFrame()

        try:
            csv_io = io.StringIO(csv_data)
            df = pd.read_csv(csv_io, header=None)

            # Row 3 (index 3) contains column names
            column_names = df.iloc[3].values

            # Drop header rows (0-3)
            df = df.drop([0, 1, 2, 3]).reset_index(drop=True)
            df.columns = column_names

            # Drop columns with NaN/empty names (first column in annotated CSV is often empty)
            df = df.loc[:, df.columns.notna()]
            df = df.loc[:, df.columns != ""]

            # Drop any remaining metadata columns
            cols_to_drop = [
                "result",
                "table",
                "_start",
                "_stop",
                "_field",
                "domain",
                "_measurement",
                "entity_id",
            ]
            df = df.drop(
                columns=[c for c in cols_to_drop if c in df.columns], errors="ignore"
            )

            # Parse _time column
            if "_time" in df.columns:
                df["_time"] = pd.to_datetime(df["_time"], utc=True)
                df["_time"] = df["_time"].dt.tz_convert(self.local_tz)
                df["_time"] = df["_time"].dt.tz_localize(
                    None
                )  # Remove tz info for easier handling
                df = df.rename(columns={"_time": "Timestamp"})
                df = df.set_index("Timestamp")

            return df

        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
            return pd.DataFrame()

    def query_energy_data(
        self, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """
        Query energy data for all configured sensors between two dates.

        Queries each sensor individually, then merges results on timestamp.
        This is more reliable than trying to pivot multiple sensors in Flux.
        """
        if not self.sensors:
            logger.warning("No sensors configured to query.")
            return pd.DataFrame()

        # Convert input dates to local timezone, then to naive for consistent handling
        if start_date.tzinfo is not None:
            start_local = start_date.astimezone(self.local_tz).replace(tzinfo=None)
        else:
            start_local = start_date

        if end_date.tzinfo is not None:
            end_local = end_date.astimezone(self.local_tz).replace(tzinfo=None)
        else:
            end_local = end_date

        # Convert to UTC strings for queries
        # Add 1 hour buffer to ensure we capture boundary data
        start_utc = self._to_utc_str(start_date)
        stop_utc = self._to_utc_str(end_date + timedelta(hours=1))

        logger.info(
            f"Querying {len(self.sensors)} sensors from {start_local} to {end_local}"
        )

        # Query each sensor individually
        dataframes = []
        for sensor in self.sensors:
            df = self._query_single_sensor(sensor, start_utc, stop_utc)
            if not df.empty:
                dataframes.append(df)

        if not dataframes:
            logger.warning("No data returned from any sensor.")
            return pd.DataFrame()

        # Merge all dataframes on timestamp index
        result = dataframes[0]
        for df in dataframes[1:]:
            result = result.join(df, how="outer")

        # Sort by timestamp
        result = result.sort_index()

        # Remove duplicate timestamps (keep last value for each hour)
        result = result[~result.index.duplicated(keep="last")]

        # Ensure we're within the requested time range (use naive local times)
        result = result.loc[start_local:end_local]  # type: ignore[misc]

        # Create a complete hourly index and reindex (naive local times)
        full_index = pd.date_range(start=start_local, end=end_local, freq="h")
        result = result.reindex(full_index)

        # Forward fill missing values (appropriate for cumulative meters)
        result = result.ffill()

        logger.info(
            f"Query returned {len(result)} hourly data points for {len(result.columns)} sensors"
        )

        return result

    def query_specific_sensors(
        self, start_date: datetime, end_date: datetime, sensor_list: list[str]
    ) -> pd.DataFrame:
        """
        Query specific sensors between two dates.

        Like query_energy_data but only queries the specified sensors.
        Much faster when only a few sensors are needed.
        """
        if not sensor_list:
            logger.warning("No sensors specified to query.")
            return pd.DataFrame()

        # Convert input dates to local timezone, then to naive for consistent handling
        if start_date.tzinfo is not None:
            start_local = start_date.astimezone(self.local_tz).replace(tzinfo=None)
        else:
            start_local = start_date

        if end_date.tzinfo is not None:
            end_local = end_date.astimezone(self.local_tz).replace(tzinfo=None)
        else:
            end_local = end_date

        # Convert to UTC strings for queries
        start_utc = self._to_utc_str(start_date)
        stop_utc = self._to_utc_str(end_date + timedelta(hours=1))

        logger.info(
            f"Querying {len(sensor_list)} specific sensors from {start_local} to {end_local}"
        )

        # Query each sensor individually
        dataframes = []
        for sensor in sensor_list:
            df = self._query_single_sensor(sensor, start_utc, stop_utc)
            if not df.empty:
                dataframes.append(df)

        if not dataframes:
            logger.warning("No data returned from any sensor.")
            return pd.DataFrame()

        # Merge all dataframes on timestamp index
        result = dataframes[0]
        for df in dataframes[1:]:
            result = result.join(df, how="outer")

        # Sort by timestamp
        result = result.sort_index()

        # Remove duplicate timestamps (keep last value for each hour)
        result = result[~result.index.duplicated(keep="last")]

        # Ensure we're within the requested time range
        result = result.loc[start_local:end_local]  # type: ignore[misc]

        # Create a complete hourly index and reindex
        full_index = pd.date_range(start=start_local, end=end_local, freq="h")
        result = result.reindex(full_index)

        # Forward fill missing values
        result = result.ffill()

        logger.info(
            f"Query returned {len(result)} hourly data points for {len(result.columns)} sensors"
        )

        return result


if __name__ == "__main__":
    # Example usage
    example_options = {
        "influxdb_url": "http://localhost:8086/api/v2/query",
        "influxdb_username": "user",
        "influxdb_password": "pass",
        "influxdb_bucket": "home_assistant/autogen",
        "sensor_gardshus": "sensor.gardshus",
        "sensor_salong": "sensor.salong",
        "sensor_electricity_price": "sensor.electricity_price",
        "sensor_energy_consumption": "sensor.energy_consumption",
    }
    service = InfluxService(example_options)
    print("Loaded sensors:", service.get_sensors())

    # Query for yesterday
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end = start + timedelta(days=1)

    df = service.query_energy_data(start_date=start, end_date=end)

    if not df.empty:
        print("\nQuery result:")
        print(df.head(10))
        print(f"\nFetched {len(df)} hourly data points for {len(df.columns)} sensors.")
    else:
        print("\nNo data returned from query.")
