"""
AEGIS InfluxDB Ingester

This module handles time-series vitals data storage in InfluxDB.
Supports both real InfluxDB and mock mode for testing.

Configuration:
- Set MOCK_INFLUX=false and provide INFLUX_* env vars for real DB
- Set MOCK_INFLUX=true (default) for testing without InfluxDB

When running with Docker, InfluxDB is automatically configured.
"""

import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
import os
from dotenv import load_dotenv
import random
from datetime import datetime, timedelta

load_dotenv()

# InfluxDB Configuration
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "aegis_org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "vitals")

# Use mock if no token provided or explicitly set
MOCK_INFLUX = os.getenv("MOCK_INFLUX", "true").lower() == "true" or not INFLUX_TOKEN

class MockWriteApi:
    def write(self, bucket, org, record):
        print(f"[MockInflux] Writing to {bucket}: {record}")

class MockQueryApi:
    def query(self, query, org):
        print(f"[MockInflux] Querying: {query}")
        # Return dummy data structure that mimics InfluxDB client response
        # We need to return an object that has a 'records' attribute which is a list of objects with get_time, get_field, get_value
        results = []
        now = datetime.now()
        for i in range(10):
            t = now - timedelta(minutes=i*5)
            results.append(MockRecord(t, "heart_rate", 60 + random.randint(0, 40)))
            results.append(MockRecord(t, "spo2", 95 + random.randint(0, 4)))
        
        return [MockTable(results)]

class MockRecord:
    def __init__(self, time, field, value):
        self._time = time
        self._field = field
        self._value = value
    
    def get_time(self):
        return self._time
    
    def get_field(self):
        return self._field
    
    def get_value(self):
        return self._value

class MockTable:
    def __init__(self, records):
        self.records = records

if not MOCK_INFLUX and INFLUX_URL:
    try:
        client = influxdb_client.InfluxDBClient(
            url=INFLUX_URL,
            token=INFLUX_TOKEN,
            org=INFLUX_ORG
        )
        write_api = client.write_api(write_options=SYNCHRONOUS)
        query_api = client.query_api()
    except Exception as e:
        print(f"Failed to connect to InfluxDB: {e}. Falling back to Mock.")
        write_api = MockWriteApi()
        query_api = MockQueryApi()
else:
    print("Using Mock InfluxDB Client")
    write_api = MockWriteApi()
    query_api = MockQueryApi()

def write_vitals(user_id: int, heart_rate: float, spo2: float):
    """
    Writes a new vital sign data point to InfluxDB tagged by user_id.
    """
    if MOCK_INFLUX:
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=f"user={user_id} hr={heart_rate} spo2={spo2}")
        return

    point = (
        influxdb_client.Point("vitals")
        .tag("user_id", str(user_id))
        .field("heart_rate", heart_rate)
        .field("spo2", spo2)
    )
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

def query_vitals(user_id: int, time_range: str = "-1h"):
    """
    Queries the last "time_range" of vitals data for the user with the given user_id
    """
    if MOCK_INFLUX:
        # Return mock data directly in the format expected by the API
        results = []
        now = datetime.now()
        for i in range(20):
            t = now - timedelta(minutes=i)
            results.append({
                "time": t,
                "field": "heart_rate",
                "value": 70 + random.randint(-5, 20)
            })
            results.append({
                "time": t,
                "field": "spo2",
                "value": 98 + random.randint(-2, 1)
            })
        # Sort by time ascending
        results.sort(key=lambda x: x["time"])
        return results

    flux_query = f"""
    from(bucket: "{INFLUX_BUCKET}")
    |> range(start: {time_range})
    |> filter(fn: (r) => r._measurement == "vitals")
    |> filter(fn: (r) => r.user_id == "{str(user_id)}")
    """
    tables = query_api.query(query=flux_query, org=INFLUX_ORG)

    results = []
    for table in tables:
        for record in table.records:
            results.append({
                "time" : record.get_time(),
                "field" : record.get_field(),
                "value" : record.get_value()
            })
    return results