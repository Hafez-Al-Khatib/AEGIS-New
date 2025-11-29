# Samsung Galaxy Watch 4 Integration Guide

AEGIS supports real-time and batch health data sync from your Samsung Galaxy Watch 4.

## 🚀 Quick Start

```bash
# 1. Start the WebSocket server for real-time data
python mcp_servers/health_connect/websocket_server.py

# 2. Or import from Samsung Health export
python scripts/sync_samsung_health.py --export-dir /path/to/export --user-id 2

# 3. Ask Sentinel about your vitals
"What's my heart rate from my watch?"
"Check my Galaxy Watch vitals"
```

## Supported Metrics

| Metric | Watch Sensor | API Field |
|--------|--------------|-----------|
| Heart Rate | Optical HR | `heart_rate` |
| Blood Oxygen (SpO2) | Red LED | `spo2` |
| Blood Pressure | BIA + Calibration | `systolic_bp`, `diastolic_bp` |
| ECG | Electrical sensor | `ecg_classification`, `ecg_heart_rate` |
| Body Composition | BIA | `body_fat_percent`, `skeletal_muscle_mass`, `body_water_percent`, `bmr` |
| Stress | HRV analysis | `stress_level` |
| Sleep | Accelerometer + HR | `sleep_score`, `sleep_duration_minutes`, `deep_sleep_minutes`, `rem_sleep_minutes` |
| Activity | Accelerometer | `steps`, `calories_burned`, `active_minutes`, `floors_climbed` |
| Skin Temperature | IR sensor (sleep) | `skin_temperature` |

---

## Integration Methods

### Method 1: Samsung Health Export (Recommended for Initial Sync)

Best for importing historical data.

1. **Export your data:**
   - Open Samsung Health app on your phone
   - Go to **Settings** → **Download personal data**
   - Select data types and export (JSON format)
   - Wait for email with download link

2. **Import to AEGIS:**
   ```bash
   python scripts/sync_samsung_health.py --export-dir /path/to/export --user-id YOUR_USER_ID
   ```

3. **Optional: Clear existing data first:**
   ```bash
   python scripts/sync_samsung_health.py --export-dir /path/to/export --user-id YOUR_USER_ID --clear
   ```

---

### Method 2: Real-time API Sync (Recommended for Ongoing)

Use a sync app like **Tasker + AutoWeb** or a custom companion app to push data to AEGIS.

#### API Endpoints

**Single Reading:**
```http
POST /vitals/watch/sync
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "heart_rate": 72,
  "spo2": 98,
  "systolic_bp": 120,
  "diastolic_bp": 80,
  "stress_level": 35,
  "steps": 5432,
  "source": "galaxy_watch_4"
}
```

**Batch Sync:**
```http
POST /vitals/watch/batch
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "readings": [
    {"heart_rate": 72, "spo2": 98, "timestamp": "2024-01-15T10:30:00"},
    {"heart_rate": 75, "spo2": 97, "timestamp": "2024-01-15T10:35:00"}
  ]
}
```

**Get Latest:**
```http
GET /vitals/watch/latest
Authorization: Bearer YOUR_TOKEN
```

---

### Method 3: Health Connect + MacroDroid (Recommended)

Best for automated, continuous real-time tracking. **No InfluxDB required!**

Health Connect is Android's unified health API (replaces Google Fit).

#### Step 1: Phone Setup
1. Install **Health Connect** from Play Store ✅ (you have this)
2. Open **Samsung Health** → Settings → Connected services
3. Enable **Health Connect** for all data types

#### Step 2: Install MacroDroid (Free)
1. Install **MacroDroid** from Play Store
2. Grant Health Connect permissions to MacroDroid

#### Step 3: Create Automation Macro

In MacroDroid, create a new macro:

**Trigger:**
- Connectivity → WiFi State Change (or Time → Every 5 minutes)

**Action:**
- Web Request → HTTP POST
- URL: `http://YOUR_PC_IP:8000/health-connect/webhook?api_key=aegis-health-key`
- Method: POST  
- Content-Type: application/json
- Body:
```json
{
  "heart_rate": [health_connect_heart_rate],
  "spo2": [health_connect_oxygen],
  "steps": [health_connect_steps]
}
```

#### Step 4: Test Connection
```bash
curl -X POST "http://localhost:8000/health-connect/webhook?api_key=aegis-health-key" \
  -H "Content-Type: application/json" \
  -d '{"heart_rate": 72, "spo2": 98, "steps": 5000}'
```

#### Benefits:
- ✅ Real-time sync via Health Connect
- ✅ No cloud API needed (on-device)
- ✅ No InfluxDB required (SQLite)
- ✅ Free (MacroDroid free tier)
- ✅ Works with any Health Connect app

---

### Method 4: Health Connect Manual Export

Health Connect is Google's unified health API that Samsung Health syncs to.

#### Setup:
1. Install **Health Connect** from Play Store
2. Open Samsung Health → Settings → Synced services → Connect to Health Connect
3. Use a Health Connect sync app to push data to AEGIS

#### Recommended Apps:
- **Health Sync** - Syncs Samsung Health to various services
- **Tasker** with Health Connect plugin
- Custom Android app using Health Connect API

---

## Tasker Automation Example

Create a Tasker profile to auto-sync vitals every hour:

1. **Profile:** Time → Every 1 Hour
2. **Task:** 
   ```
   A1: HTTP Request [
     Method: POST
     URL: https://your-aegis-server.com/vitals/watch/sync
     Headers: Authorization: Bearer YOUR_TOKEN
     Body: {"heart_rate": %HRMONITOR, "steps": %STEPS}
   ]
   ```

---

## Dashboard Integration

Once synced, your watch vitals will appear in:

1. **Dashboard** - Real-time heart rate and SpO2 charts
2. **Chat** - Ask Sentinel "How is my heart rate today?"
3. **Alerts** - Automatic alerts for:
   - Heart rate < 40 or > 150 bpm
   - SpO2 < 90%
   - Blood pressure > 180/120 or < 80/50

---

## Troubleshooting

### No data appearing?
1. Check that your watch is syncing to Samsung Health
2. Verify the export contains JSON files
3. Check user ID is correct

### Duplicate data?
Run with `--clear` flag to remove existing data before import.

### ECG not syncing?
ECG data may not be included in exports for some regions. Use the real-time API with Samsung Health Monitor app.

---

## Security Notes

- All API endpoints require authentication
- Data is stored in your local AEGIS database
- No data is shared with external services
- Blood pressure requires calibration with a certified cuff for accuracy
