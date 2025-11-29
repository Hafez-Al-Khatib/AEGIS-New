#!/usr/bin/env python3
"""
AEGIS Vitals Simulator

Simulates real-time vitals data for testing the AEGIS system.
Supports two modes:
1. Direct DB mode: Writes directly to database (for local development)
2. API mode: Posts to API endpoint (for Docker/production testing)

Usage:
    # Direct DB mode (local development)
    python scripts/simulate_vitals.py --user-id 2 --interval 5

    # API mode (Docker testing)
    python scripts/simulate_vitals.py --api-mode --api-url http://localhost:8000

    # Simulate critical vitals (to test emergency call)
    python scripts/simulate_vitals.py --critical --user-id 2

This script is used for:
- Testing without Galaxy Watch hardware
- Demo purposes
- Emergency call system testing
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import argparse
import time
import random
import requests
from datetime import datetime

# Only import DB modules if not in API mode
try:
    from database import SessionLocal
    from models import HealthEvent, User
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

def simulate_vitals(csv_path: str, user_id: int, interval: float = 2.0):
    """
    Continuously feed vitals from CSV with real-time timestamps.
    
    Args:
        csv_path: Path to the CSV file
        user_id: Target user ID
        interval: Seconds between each reading
    """
    session = SessionLocal()
    
    try:
        # Verify user exists
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"❌ User {user_id} not found!")
            return
        
        print(f"🔄 Starting vitals simulation for user: {user.email} (ID: {user_id})")
        print(f"   Interval: {interval}s between readings")
        print(f"   Press Ctrl+C to stop\n")
        
        # Read CSV
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"📊 Loaded {len(rows)} records from CSV\n")
        
        idx = 0
        while True:
            row = rows[idx % len(rows)]  # Loop through data
            
            # Extract vitals
            heart_rate = row.get('heartrate', '').strip()
            spo2 = row.get('o2sat', '').strip()
            temp = row.get('temperature', '').strip()
            sbp = row.get('sbp', '').strip()
            dbp = row.get('dbp', '').strip()
            
            if not heart_rate and not spo2:
                idx += 1
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
            
            # Create health event with CURRENT timestamp
            event = HealthEvent(
                user_id=user_id,
                event_type="vitals",
                data=data,
                timestamp=datetime.now()
            )
            session.add(event)
            session.commit()
            
            # Display
            hr_str = f"HR: {data.get('heart_rate', '--'):.0f}" if data.get('heart_rate') else "HR: --"
            spo2_str = f"SpO2: {data.get('spo2', '--'):.0f}%" if data.get('spo2') else "SpO2: --"
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {hr_str} | {spo2_str}")
            
            idx += 1
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\n✅ Simulation stopped. Inserted {idx} records.")
    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
    finally:
        session.close()

def simulate_via_api(api_url: str, api_key: str, interval: float = 30.0, critical: bool = False):
    """
    Simulate vitals by posting to the Health Connect API endpoint.
    Works in Docker containers without direct DB access.
    """
    print(f"🌐 API Mode - Posting to: {api_url}/health-connect/webhook")
    print(f"   Interval: {interval}s | Critical mode: {critical}")
    print(f"   Press Ctrl+C to stop\n")
    
    idx = 0
    try:
        while True:
            if critical:
                # Generate critical vitals to trigger emergency
                hr = random.choice([35, 38, 155, 165, 170])  # Critical HR
                spo2 = random.choice([82, 85, 87])  # Critical SpO2
                status = "🚨 CRITICAL"
            else:
                # Normal vitals
                hr = random.randint(65, 95)
                spo2 = random.randint(95, 99)
                status = "✅ Normal"
            
            payload = {
                "api_key": api_key,
                "heart_rate": hr,
                "spo2": spo2,
                "source_app": "aegis_simulator",
                "device": "test_device"
            }
            
            try:
                resp = requests.post(
                    f"{api_url}/health-connect/webhook",
                    json=payload,
                    timeout=10
                )
                
                if resp.status_code == 200:
                    result = resp.json()
                    emergency = "🚨 EMERGENCY TRIGGERED!" if result.get("status") == "EMERGENCY" else ""
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] HR: {hr} | SpO2: {spo2}% | {status} {emergency}")
                else:
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] ❌ API Error: {resp.status_code}")
                    
            except requests.RequestException as e:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] ❌ Connection error: {e}")
            
            idx += 1
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\n✅ Simulation stopped. Sent {idx} readings.")


def simulate_critical_db(user_id: int, count: int = 5, interval: float = 10.0):
    """
    Simulate critical vitals directly to DB to test emergency auto-trigger.
    Sends 'count' critical readings to trigger sustained critical detection.
    """
    if not DB_AVAILABLE:
        print("❌ Database modules not available. Use --api-mode instead.")
        return
    
    session = SessionLocal()
    
    print(f"🚨 CRITICAL VITALS SIMULATION")
    print(f"   User ID: {user_id}")
    print(f"   Sending {count} critical readings at {interval}s intervals")
    print(f"   This WILL trigger emergency call if Twilio is configured!\n")
    
    try:
        for i in range(count):
            # Critically high heart rate
            hr = random.randint(155, 175)
            spo2 = random.randint(82, 87)
            
            data = {
                "heart_rate": hr,
                "spo2": spo2,
                "source": "critical_test"
            }
            
            event = HealthEvent(
                user_id=user_id,
                event_type="vitals",
                data=data,
                timestamp=datetime.now()
            )
            session.add(event)
            session.commit()
            
            print(f"  [{i+1}/{count}] 🚨 HR: {hr} bpm | SpO2: {spo2}%")
            
            if i < count - 1:
                time.sleep(interval)
        
        print(f"\n✅ Sent {count} critical readings.")
        print("   Check logs for emergency call trigger!")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description='AEGIS Vitals Simulator - Test vitals without hardware',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Normal CSV-based simulation (local dev)
  python simulate_vitals.py --user-id 2 --interval 5

  # API mode for Docker testing
  python simulate_vitals.py --api-mode --api-url http://localhost:8000

  # Trigger emergency call test (5 critical readings)
  python simulate_vitals.py --critical --user-id 2

  # API mode with critical vitals
  python simulate_vitals.py --api-mode --critical --api-url http://localhost:8000
        """
    )
    parser.add_argument('--csv', default='vitalsigns/vitalsign.csv', help='Path to CSV file')
    parser.add_argument('--user-id', type=int, default=2, help='User ID')
    parser.add_argument('--interval', type=float, default=2.0, help='Seconds between readings')
    parser.add_argument('--api-mode', action='store_true', help='Use API endpoint instead of direct DB')
    parser.add_argument('--api-url', default=os.getenv('API_URL', 'http://localhost:8000'), help='API base URL')
    parser.add_argument('--api-key', default=os.getenv('API_KEY', 'aegis-health-key'), help='Health Connect API key')
    parser.add_argument('--critical', action='store_true', help='Simulate critical vitals (triggers emergency)')
    parser.add_argument('--critical-count', type=int, default=5, help='Number of critical readings to send')
    
    args = parser.parse_args()
    
    # API mode
    if args.api_mode:
        simulate_via_api(args.api_url, args.api_key, args.interval, args.critical)
        return
    
    # Critical test mode (direct DB)
    if args.critical:
        simulate_critical_db(args.user_id, args.critical_count, args.interval)
        return
    
    # CSV mode (original behavior)
    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), args.csv)
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return
    
    simulate_vitals(csv_path, args.user_id, args.interval)

if __name__ == "__main__":
    main()
