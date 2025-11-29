"""
Ingest vital signs from CSV into HealthEvents table.
Usage: python scripts/ingest_vitals_csv.py --user-id 2 --limit 500
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import argparse
from datetime import datetime, timedelta
from database import SessionLocal
from models import HealthEvent, User
import random

def parse_datetime(dt_str):
    """Parse the MIMIC datetime format and shift to recent dates."""
    try:
        original = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        # Shift old dates to recent (within last 7 days for testing)
        days_ago = random.randint(0, 6)
        hours_offset = random.randint(0, 23)
        minutes_offset = random.randint(0, 59)
        new_time = datetime.now() - timedelta(days=days_ago, hours=hours_offset, minutes=minutes_offset)
        return new_time
    except:
        return datetime.now()

def ingest_vitals(csv_path: str, user_id: int, limit: int = 500, clear_existing: bool = False):
    """
    Ingest vitals from CSV file into database.
    
    Args:
        csv_path: Path to the CSV file
        user_id: Target user ID to associate vitals with
        limit: Max number of records to ingest
        clear_existing: If True, delete existing vitals for user first
    """
    session = SessionLocal()
    
    try:
        # Verify user exists
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"❌ User {user_id} not found!")
            return
        
        print(f"📊 Ingesting vitals for user: {user.email} (ID: {user_id})")
        
        # Optionally clear existing
        if clear_existing:
            deleted = session.query(HealthEvent).filter(
                HealthEvent.user_id == user_id,
                HealthEvent.event_type == "vitals"
            ).delete()
            session.commit()
            print(f"🗑️  Cleared {deleted} existing vitals records")
        
        # Read CSV and ingest
        count = 0
        skipped = 0
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                if count >= limit:
                    break
                
                # Extract vitals (skip if both heart rate and spo2 are empty)
                heart_rate = row.get('heartrate', '').strip()
                spo2 = row.get('o2sat', '').strip()
                temp = row.get('temperature', '').strip()
                sbp = row.get('sbp', '').strip()
                dbp = row.get('dbp', '').strip()
                resp_rate = row.get('resprate', '').strip()
                
                if not heart_rate and not spo2:
                    skipped += 1
                    continue
                
                # Build data payload
                data = {}
                if heart_rate:
                    data['heart_rate'] = float(heart_rate)
                if spo2:
                    data['spo2'] = float(spo2)
                if temp:
                    data['temperature'] = float(temp)
                if sbp:
                    data['systolic_bp'] = int(float(sbp))
                if dbp:
                    data['diastolic_bp'] = int(float(dbp))
                if resp_rate:
                    data['respiratory_rate'] = float(resp_rate)
                
                # Create health event with shifted timestamp
                event = HealthEvent(
                    user_id=user_id,
                    event_type="vitals",
                    data=data,
                    timestamp=parse_datetime(row.get('charttime', ''))
                )
                session.add(event)
                count += 1
                
                # Batch commit every 100 records
                if count % 100 == 0:
                    session.commit()
                    print(f"  📈 Ingested {count} records...")
        
        # Final commit
        session.commit()
        print(f"\n✅ Successfully ingested {count} vitals records (skipped {skipped} empty)")
        
        # Show sample
        sample = session.query(HealthEvent).filter(
            HealthEvent.user_id == user_id,
            HealthEvent.event_type == "vitals"
        ).order_by(HealthEvent.timestamp.desc()).first()
        
        if sample:
            print(f"\n📋 Latest record sample:")
            print(f"   Timestamp: {sample.timestamp}")
            print(f"   Data: {sample.data}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        session.close()

def main():
    parser = argparse.ArgumentParser(description='Ingest vitals CSV into database')
    parser.add_argument('--csv', default='vitalsigns/vitalsign.csv', help='Path to CSV file')
    parser.add_argument('--user-id', type=int, default=2, help='User ID to associate vitals with')
    parser.add_argument('--limit', type=int, default=500, help='Max records to ingest')
    parser.add_argument('--clear', action='store_true', help='Clear existing vitals first')
    
    args = parser.parse_args()
    
    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), args.csv)
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return
    
    print(f"🔄 Starting vitals ingestion...")
    print(f"   CSV: {csv_path}")
    print(f"   User ID: {args.user_id}")
    print(f"   Limit: {args.limit}")
    print()
    
    ingest_vitals(csv_path, args.user_id, args.limit, args.clear)

if __name__ == "__main__":
    main()
