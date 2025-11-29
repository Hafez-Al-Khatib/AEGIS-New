"""
Health Connect Integration for AEGIS

Health Connect is Android's unified health data platform that replaces Google Fit.
Samsung Health syncs directly to Health Connect on Android 14+.

Since Health Connect is an on-device API (no cloud REST API), we use two approaches:

1. WEBHOOK MODE: Receive data pushed from Android automation apps
2. EXPORT MODE: Import Health Connect data exports

For real-time sync, use one of these Android apps:
- MacroDroid (free) - Trigger on health data change
- Tasker + AutoHealth plugin
- Health Sync app
- Custom app with Health Connect SDK

Setup:
1. Install Health Connect on your phone
2. Connect Samsung Health to Health Connect
3. Use MacroDroid/Tasker to POST data to AEGIS webhook
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import SessionLocal
from models import HealthEvent, User

# ============== SCHEMAS ==============

class HealthConnectReading(BaseModel):
    """Health Connect / Health Sync data format from Android."""
    # Vitals - multiple naming conventions supported
    heart_rate: Optional[float] = None
    heartRate: Optional[float] = None  # Health Sync format
    hr: Optional[float] = None  # Alternative
    
    heart_rate_variability: Optional[float] = None
    hrv: Optional[float] = None
    resting_heart_rate: Optional[float] = None
    restingHeartRate: Optional[float] = None
    
    spo2: Optional[float] = None  # Blood oxygen
    bloodOxygen: Optional[float] = None  # Health Sync format
    oxygenSaturation: Optional[float] = None
    
    respiratory_rate: Optional[float] = None
    respiratoryRate: Optional[float] = None
    
    # Blood Pressure
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    bloodPressureSystolic: Optional[int] = None
    bloodPressureDiastolic: Optional[int] = None
    
    # Body
    weight_kg: Optional[float] = None
    weight: Optional[float] = None
    height_cm: Optional[float] = None
    height: Optional[float] = None
    body_fat_percent: Optional[float] = None
    bodyFat: Optional[float] = None
    body_temperature: Optional[float] = None
    temperature: Optional[float] = None
    
    # Activity
    steps: Optional[int] = None
    stepCount: Optional[int] = None  # Health Sync format
    distance_meters: Optional[float] = None
    distance: Optional[float] = None
    calories_burned: Optional[float] = None
    calories: Optional[float] = None
    activeCalories: Optional[float] = None
    floors_climbed: Optional[int] = None
    floors: Optional[int] = None
    active_minutes: Optional[int] = None
    activeMinutes: Optional[int] = None
    
    # Sleep
    sleep_duration_minutes: Optional[int] = None
    sleepDuration: Optional[int] = None
    sleep_stages: Optional[Dict] = None  # {deep, light, rem, awake}
    
    # Stress (Samsung Health specific)
    stress: Optional[int] = None
    stressLevel: Optional[int] = None
    
    # Metadata
    timestamp: Optional[str] = None
    date: Optional[str] = None  # Alternative timestamp
    source_app: Optional[str] = "health_connect"
    source: Optional[str] = None
    device: Optional[str] = "samsung_galaxy_watch"
    
    class Config:
        extra = "allow"  # Accept any additional fields


class HealthConnectBatch(BaseModel):
    """Batch of Health Connect readings."""
    readings: List[HealthConnectReading]
    api_key: Optional[str] = None  # Simple auth for webhook


# ============== WEBHOOK ROUTER ==============

router = APIRouter(prefix="/health-connect", tags=["Health Connect"])


def get_user_from_key(api_key: str, db) -> Optional[User]:
    """Get user from simple API key (stored in env or user profile)."""
    # For simplicity, check against env variable
    # In production, store per-user API keys in database
    expected_key = os.getenv("HEALTH_CONNECT_API_KEY", "aegis-health-key")
    if api_key == expected_key:
        # Return default user (or query by key)
        return db.query(User).first()
    return None


@router.post("/webhook")
async def health_connect_webhook(data: HealthConnectReading, api_key: str = None):
    """
    Webhook endpoint for Health Connect data from Android.
    
    Configure MacroDroid/Tasker to POST to:
    http://YOUR_SERVER:8000/health-connect/webhook?api_key=YOUR_KEY
    """
    session = SessionLocal()
    
    try:
        # Simple API key auth
        expected_key = os.getenv("HEALTH_CONNECT_API_KEY", "aegis-health-key")
        if api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # Get user (default to user 2 for now)
        user_id = int(os.getenv("HEALTH_CONNECT_USER_ID", "2"))
        
        # Build vitals data - normalize all field name variants
        vitals = {}
        
        # Heart rate (multiple possible field names)
        hr = data.heart_rate or data.heartRate or data.hr
        if hr:
            vitals['heart_rate'] = hr
        
        # SpO2 / Blood oxygen
        spo2 = data.spo2 or data.bloodOxygen or data.oxygenSaturation
        if spo2:
            vitals['spo2'] = spo2
        
        # Blood pressure
        systolic = data.systolic or data.bloodPressureSystolic
        diastolic = data.diastolic or data.bloodPressureDiastolic
        if systolic and diastolic:
            vitals['systolic_bp'] = systolic
            vitals['diastolic_bp'] = diastolic
        
        # Steps
        steps = data.steps or data.stepCount
        if steps:
            vitals['steps'] = steps
        
        # Calories
        calories = data.calories_burned or data.calories or data.activeCalories
        if calories:
            vitals['calories_burned'] = calories
        
        # Temperature
        temp = data.body_temperature or data.temperature
        if temp:
            vitals['temperature'] = temp
        
        # Respiratory rate
        resp = data.respiratory_rate or data.respiratoryRate
        if resp:
            vitals['respiratory_rate'] = resp
        
        # Resting heart rate
        rhr = data.resting_heart_rate or data.restingHeartRate
        if rhr:
            vitals['resting_heart_rate'] = rhr
        
        # Stress level (Samsung Health)
        stress = data.stress or data.stressLevel
        if stress:
            vitals['stress_level'] = stress
        
        # Sleep
        sleep = data.sleep_duration_minutes or data.sleepDuration
        if sleep:
            vitals['sleep_minutes'] = sleep
        
        # HRV
        hrv = data.heart_rate_variability or data.hrv
        if hrv:
            vitals['hrv'] = hrv
        
        # Weight & body composition
        if data.weight_kg or data.weight:
            vitals['weight_kg'] = data.weight_kg or data.weight
        if data.body_fat_percent or data.bodyFat:
            vitals['body_fat_percent'] = data.body_fat_percent or data.bodyFat
        
        vitals['source'] = data.source_app or data.source or 'health_sync'
        vitals['device'] = data.device or 'galaxy_watch'
        
        # Parse timestamp
        timestamp = datetime.utcnow()
        if data.timestamp:
            try:
                timestamp = datetime.fromisoformat(data.timestamp.replace('Z', '+00:00'))
            except:
                pass
        
        # Save to database
        event = HealthEvent(
            user_id=user_id,
            event_type="vitals",
            data=vitals,
            timestamp=timestamp
        )
        session.add(event)
        session.commit()
        
        print(f"[HEALTH CONNECT] Saved: HR={data.heart_rate}, SpO2={data.spo2}, Steps={data.steps}")
        
        # Check for alerts
        alerts = []
        if data.heart_rate and (data.heart_rate < 40 or data.heart_rate > 150):
            alerts.append(f"Heart rate {data.heart_rate} bpm is abnormal")
        if data.spo2 and data.spo2 < 90:
            alerts.append(f"SpO2 {data.spo2}% is critically low")
        
        # Check for sustained critical vitals and auto-trigger emergency call
        emergency_result = None
        try:
            from integrations.twilio_emergency import auto_trigger_emergency_if_critical
            emergency_result = auto_trigger_emergency_if_critical(user_id, vitals)
        except Exception as e:
            print(f"[EMERGENCY CHECK ERROR] {e}")
        
        response = {
            "status": "success",
            "event_id": event.id,
            "alerts": alerts
        }
        
        if emergency_result:
            response["emergency_call"] = emergency_result
            response["status"] = "EMERGENCY"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.post("/webhook/batch")
async def health_connect_batch_webhook(batch: HealthConnectBatch):
    """Batch webhook for multiple readings."""
    session = SessionLocal()
    saved = 0
    
    try:
        expected_key = os.getenv("HEALTH_CONNECT_API_KEY", "aegis-health-key")
        if batch.api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        user_id = int(os.getenv("HEALTH_CONNECT_USER_ID", "2"))
        
        for reading in batch.readings:
            vitals = {
                k: v for k, v in reading.dict().items()
                if v is not None and k not in ['timestamp', 'source_app', 'device', 'sleep_stages']
            }
            vitals['source'] = reading.source_app or 'health_connect'
            
            event = HealthEvent(
                user_id=user_id,
                event_type="vitals",
                data=vitals,
                timestamp=datetime.fromisoformat(reading.timestamp) if reading.timestamp else datetime.utcnow()
            )
            session.add(event)
            saved += 1
        
        session.commit()
        print(f"[HEALTH CONNECT] Batch saved {saved} readings")
        
        return {"status": "success", "saved": saved}
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/status")
async def health_connect_status():
    """Check Health Connect integration status."""
    session = SessionLocal()
    
    try:
        # Get latest Health Connect reading
        latest = session.query(HealthEvent).filter(
            HealthEvent.event_type == "vitals"
        ).order_by(HealthEvent.timestamp.desc()).first()
        
        if latest and latest.data.get('source') in ['health_connect', 'galaxy_watch']:
            return {
                "status": "connected",
                "last_sync": latest.timestamp.isoformat(),
                "last_data": latest.data
            }
        
        return {
            "status": "waiting",
            "message": "No Health Connect data received yet. Configure your Android app to POST to /health-connect/webhook"
        }
    finally:
        session.close()


# ============== MACRODROID TEMPLATE ==============

MACRODROID_TEMPLATE = """
MACRODROID SETUP FOR HEALTH CONNECT → AEGIS

1. Install MacroDroid from Play Store (free)

2. Create new Macro:
   
   TRIGGER: 
   - Fitness/Health → Health Connect Data Changed
   - Select: Heart Rate, SpO2, Steps
   
   ACTION:
   - Web Request (HTTP POST)
   - URL: http://YOUR_AEGIS_IP:8000/health-connect/webhook?api_key=aegis-health-key
   - Method: POST
   - Content-Type: application/json
   - Body:
     {
       "heart_rate": {health_connect_heart_rate},
       "spo2": {health_connect_spo2},
       "steps": {health_connect_steps},
       "timestamp": "{datetime_iso}"
     }

3. Grant permissions:
   - MacroDroid → Health Connect access
   - Samsung Health → Health Connect sync enabled

4. Test the macro manually first

ALTERNATIVE - Use HTTP Shortcuts app:
1. Create shortcut with POST to webhook URL
2. Add widget to home screen
3. Tap to sync current vitals
"""


def print_setup_guide():
    """Print setup guide for Health Connect."""
    print("=" * 60)
    print("🏥 AEGIS Health Connect Setup Guide")
    print("=" * 60)
    print("""
STEP 1: Phone Setup
-------------------
1. Install 'Health Connect' from Play Store
2. Open Samsung Health → Settings → Connected services
3. Enable 'Health Connect' for all data types

STEP 2: Automation App (Choose One)
------------------------------------
Option A: MacroDroid (Recommended - Free)
- Install from Play Store
- Create macro: Health Connect trigger → HTTP POST action
- URL: http://YOUR_PC_IP:8000/health-connect/webhook?api_key=aegis-health-key

Option B: Tasker + AutoHealth
- More powerful but paid

Option C: HTTP Shortcuts (Manual sync)
- Create POST shortcut, tap to sync

STEP 3: Test Connection
-----------------------
curl -X POST "http://localhost:8000/health-connect/webhook?api_key=aegis-health-key" \\
  -H "Content-Type: application/json" \\
  -d '{"heart_rate": 72, "spo2": 98, "steps": 5000}'

STEP 4: Verify in AEGIS
-----------------------
Ask Sentinel: "What's my heart rate from my watch?"
""")
    print(MACRODROID_TEMPLATE)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Health Connect Integration')
    parser.add_argument('--setup', action='store_true', help='Show setup guide')
    parser.add_argument('--test', action='store_true', help='Test webhook locally')
    
    args = parser.parse_args()
    
    if args.setup:
        print_setup_guide()
    elif args.test:
        import requests
        try:
            resp = requests.post(
                "http://localhost:8000/health-connect/webhook",
                params={"api_key": "aegis-health-key"},
                json={"heart_rate": 72, "spo2": 98, "steps": 5000}
            )
            print(f"Response: {resp.json()}")
        except Exception as e:
            print(f"Error: {e}")
            print("Make sure AEGIS server is running!")
    else:
        print_setup_guide()
