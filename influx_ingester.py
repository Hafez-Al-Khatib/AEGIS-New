import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
import os
from dotenv import load_dotenv

load_dotenv()

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

client = influxdb_client.InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG
)

write_api = client.write_api(write_options=SYNCHRONOUS)
query_api = client.query_api()

def write_vitals(user_id: int, heart_rate: float, spo2: float, temperature: float = None):
    """
    Writes a new vital sign data point to InfluxDB tagged by user_id.
    """
    point = (
        influxdb_client.Point("vitals")
        .tag("user_id", str(user_id))
        .field("heart_rate", heart_rate)
        .field("spo2", spo2)
    )
    if temperature is not None:
        point.field("temperature", temperature)
    
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

def query_vitals(user_id: int, time_range: str = "-1h"):
    """
    Queries the last "time_range" of vitals data for the user with the given user_id
    """
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


    