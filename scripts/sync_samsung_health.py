"""
Samsung Galaxy Watch 4 / Samsung Health Data Sync Script

This script imports health data exported from Samsung Health app into AEGIS.

SETUP:
1. Open Samsung Health app on your phone
2. Go to Settings > Download personal data
3. Export your data (JSON format)
4. Extract the zip and run this script

Usage:
    python scripts/sync_samsung_health.py --export-dir /path/to/samsung_health_export --user-id 2

Alternatively, use Health Connect API with the companion app.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import argparse
from datetime import datetime
from pathlib import Path
from database import SessionLocal
from models import HealthEvent, User

def parse_samsung_datetime(dt_str):
    """Parse Samsung Health datetime format."""
    try:
        # Samsung uses various formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S.%f"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_str, fmt)
            except:
                continue
        return datetime.now()
    except:
        return datetime.now()

def sync_heart_rate(export_dir: Path, session, user_id: int):
    """Sync heart rate data from Samsung Health export."""
    hr_file = export_dir / "com.samsung.shealth.tracker.heart_rate" / "com.samsung.shealth.tracker.heart_rate.json"
    
    if not hr_file.exists():
        # Try alternate location
        for f in export_dir.rglob("*heart_rate*.json"):
            hr_file = f
            break
    
    if not hr_file.exists():
        print("  ⚠️  No heart rate data found")
        return 0
    
    count = 0
    with open(hr_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
        records = data if isinstance(data, list) else data.get('data', [])
        
        for record in records:
            hr = record.get('heart_rate') or record.get('com.samsung.health.heart_rate.heart_rate')
            timestamp = record.get('start_time') or record.get('com.samsung.health.heart_rate.start_time')
            
            if hr:
                event = HealthEvent(
                    user_id=user_id,
                    event_type="vitals",
                    data={
                        "heart_rate": float(hr),
                        "source": "samsung_health_export"
                    },
                    timestamp=parse_samsung_datetime(timestamp) if timestamp else datetime.now()
                )
                session.add(event)
                count += 1
    
    return count

def sync_blood_oxygen(export_dir: Path, session, user_id: int):
    """Sync SpO2 data from Samsung Health export."""
    spo2_file = None
    for f in export_dir.rglob("*oxygen*.json"):
        spo2_file = f
        break
    
    if not spo2_file or not spo2_file.exists():
        print("  ⚠️  No blood oxygen data found")
        return 0
    
    count = 0
    with open(spo2_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        records = data if isinstance(data, list) else data.get('data', [])
        
        for record in records:
            spo2 = record.get('spo2') or record.get('oxygen_saturation')
            timestamp = record.get('start_time') or record.get('timestamp')
            
            if spo2:
                event = HealthEvent(
                    user_id=user_id,
                    event_type="vitals",
                    data={
                        "spo2": float(spo2),
                        "source": "samsung_health_export"
                    },
                    timestamp=parse_samsung_datetime(timestamp) if timestamp else datetime.now()
                )
                session.add(event)
                count += 1
    
    return count

def sync_blood_pressure(export_dir: Path, session, user_id: int):
    """Sync blood pressure data from Samsung Health export."""
    bp_file = None
    for f in export_dir.rglob("*blood_pressure*.json"):
        bp_file = f
        break
    
    if not bp_file or not bp_file.exists():
        print("  ⚠️  No blood pressure data found")
        return 0
    
    count = 0
    with open(bp_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        records = data if isinstance(data, list) else data.get('data', [])
        
        for record in records:
            systolic = record.get('systolic') or record.get('com.samsung.health.blood_pressure.systolic')
            diastolic = record.get('diastolic') or record.get('com.samsung.health.blood_pressure.diastolic')
            timestamp = record.get('start_time') or record.get('timestamp')
            
            if systolic and diastolic:
                event = HealthEvent(
                    user_id=user_id,
                    event_type="vitals",
                    data={
                        "systolic_bp": int(systolic),
                        "diastolic_bp": int(diastolic),
                        "source": "samsung_health_export"
                    },
                    timestamp=parse_samsung_datetime(timestamp) if timestamp else datetime.now()
                )
                session.add(event)
                count += 1
    
    return count

def sync_sleep(export_dir: Path, session, user_id: int):
    """Sync sleep data from Samsung Health export."""
    sleep_file = None
    for f in export_dir.rglob("*sleep*.json"):
        sleep_file = f
        break
    
    if not sleep_file or not sleep_file.exists():
        print("  ⚠️  No sleep data found")
        return 0
    
    count = 0
    with open(sleep_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        records = data if isinstance(data, list) else data.get('data', [])
        
        for record in records:
            event = HealthEvent(
                user_id=user_id,
                event_type="sleep",
                data={
                    "sleep_duration_minutes": record.get('duration', 0) // 60000,  # ms to min
                    "sleep_score": record.get('sleep_score'),
                    "deep_sleep_minutes": record.get('deep_sleep', 0) // 60000,
                    "rem_sleep_minutes": record.get('rem_sleep', 0) // 60000,
                    "source": "samsung_health_export"
                },
                timestamp=parse_samsung_datetime(record.get('end_time', ''))
            )
            session.add(event)
            count += 1
    
    return count

def sync_stress(export_dir: Path, session, user_id: int):
    """Sync stress data from Samsung Health export."""
    stress_file = None
    for f in export_dir.rglob("*stress*.json"):
        stress_file = f
        break
    
    if not stress_file or not stress_file.exists():
        print("  ⚠️  No stress data found")
        return 0
    
    count = 0
    with open(stress_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        records = data if isinstance(data, list) else data.get('data', [])
        
        for record in records:
            stress = record.get('score') or record.get('stress_score')
            if stress:
                event = HealthEvent(
                    user_id=user_id,
                    event_type="vitals",
                    data={
                        "stress_level": int(stress),
                        "source": "samsung_health_export"
                    },
                    timestamp=parse_samsung_datetime(record.get('start_time', ''))
                )
                session.add(event)
                count += 1
    
    return count

def sync_steps(export_dir: Path, session, user_id: int):
    """Sync step count data from Samsung Health export."""
    steps_file = None
    for f in export_dir.rglob("*step_count*.json"):
        steps_file = f
        break
    if not steps_file:
        for f in export_dir.rglob("*pedometer*.json"):
            steps_file = f
            break
    
    if not steps_file or not steps_file.exists():
        print("  ⚠️  No steps data found")
        return 0
    
    count = 0
    with open(steps_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        records = data if isinstance(data, list) else data.get('data', [])
        
        for record in records:
            steps = record.get('count') or record.get('step_count')
            calories = record.get('calorie') or record.get('calories')
            
            if steps:
                event = HealthEvent(
                    user_id=user_id,
                    event_type="activity",
                    data={
                        "steps": int(steps),
                        "calories_burned": int(calories) if calories else None,
                        "source": "samsung_health_export"
                    },
                    timestamp=parse_samsung_datetime(record.get('start_time', ''))
                )
                session.add(event)
                count += 1
    
    return count

def main():
    parser = argparse.ArgumentParser(description='Sync Samsung Health data export to AEGIS')
    parser.add_argument('--export-dir', required=True, help='Path to Samsung Health export directory')
    parser.add_argument('--user-id', type=int, required=True, help='User ID to associate data with')
    parser.add_argument('--clear', action='store_true', help='Clear existing data first')
    
    args = parser.parse_args()
    
    export_dir = Path(args.export_dir)
    if not export_dir.exists():
        print(f"❌ Export directory not found: {export_dir}")
        return
    
    session = SessionLocal()
    
    try:
        # Verify user exists
        user = session.query(User).filter(User.id == args.user_id).first()
        if not user:
            print(f"❌ User {args.user_id} not found!")
            return
        
        print(f"📱 Syncing Samsung Health data for user: {user.email}")
        print(f"   Export directory: {export_dir}")
        print()
        
        if args.clear:
            deleted = session.query(HealthEvent).filter(
                HealthEvent.user_id == args.user_id
            ).delete()
            session.commit()
            print(f"🗑️  Cleared {deleted} existing records")
        
        total = 0
        
        print("📊 Syncing heart rate...")
        count = sync_heart_rate(export_dir, session, args.user_id)
        print(f"   ✓ {count} records")
        total += count
        
        print("🫁 Syncing blood oxygen (SpO2)...")
        count = sync_blood_oxygen(export_dir, session, args.user_id)
        print(f"   ✓ {count} records")
        total += count
        
        print("💓 Syncing blood pressure...")
        count = sync_blood_pressure(export_dir, session, args.user_id)
        print(f"   ✓ {count} records")
        total += count
        
        print("😴 Syncing sleep data...")
        count = sync_sleep(export_dir, session, args.user_id)
        print(f"   ✓ {count} records")
        total += count
        
        print("😰 Syncing stress data...")
        count = sync_stress(export_dir, session, args.user_id)
        print(f"   ✓ {count} records")
        total += count
        
        print("🚶 Syncing steps/activity...")
        count = sync_steps(export_dir, session, args.user_id)
        print(f"   ✓ {count} records")
        total += count
        
        session.commit()
        print()
        print(f"✅ Successfully synced {total} total records from Samsung Health")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()
