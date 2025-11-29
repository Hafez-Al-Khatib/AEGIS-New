"""
Google Fit API Integration for AEGIS

Provides continuous real-time health data sync from Samsung Galaxy Watch
via Google Fit cloud sync.

Setup:
1. Enable Google Fit API in Google Cloud Console
2. Create OAuth 2.0 credentials (Desktop app)
3. Download credentials.json to this folder
4. Run: python google_fit.py --setup

Samsung Watch Setup:
1. Install Google Fit on your phone
2. Open Samsung Health → Settings → Connected Services → Google Fit
3. Enable sync for all health data
"""

import os
import json
import pickle
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

# Google API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    print("Google API libraries not installed. Run:")
    print("  pip install google-api-python-client google-auth-oauthlib")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import SessionLocal
from models import HealthEvent

# Google Fit API scopes
SCOPES = [
    'https://www.googleapis.com/auth/fitness.heart_rate.read',
    'https://www.googleapis.com/auth/fitness.oxygen_saturation.read',
    'https://www.googleapis.com/auth/fitness.blood_pressure.read',
    'https://www.googleapis.com/auth/fitness.body.read',
    'https://www.googleapis.com/auth/fitness.activity.read',
    'https://www.googleapis.com/auth/fitness.sleep.read',
]

# Data type mappings
DATA_TYPES = {
    'heart_rate': 'com.google.heart_rate.bpm',
    'spo2': 'com.google.oxygen_saturation',
    'blood_pressure': 'com.google.blood_pressure',
    'steps': 'com.google.step_count.delta',
    'calories': 'com.google.calories.expended',
    'sleep': 'com.google.sleep.segment',
    'weight': 'com.google.weight',
    'body_fat': 'com.google.body.fat.percentage',
}

CREDENTIALS_FILE = Path(__file__).parent / 'credentials.json'
TOKEN_FILE = Path(__file__).parent / 'token.pickle'


class GoogleFitSync:
    """Continuous Google Fit sync for AEGIS."""
    
    def __init__(self, user_id: int = 2):
        self.user_id = user_id
        self.service = None
        self.last_sync = None
        
    def authenticate(self) -> bool:
        """Authenticate with Google Fit API."""
        if not GOOGLE_API_AVAILABLE:
            print("❌ Google API libraries not installed")
            return False
            
        creds = None
        
        # Load existing token
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        
        # Refresh or get new token
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDENTIALS_FILE.exists():
                    print(f"❌ Credentials file not found: {CREDENTIALS_FILE}")
                    print("\nTo set up Google Fit API:")
                    print("1. Go to https://console.cloud.google.com/")
                    print("2. Create a project and enable 'Fitness API'")
                    print("3. Create OAuth 2.0 credentials (Desktop app)")
                    print("4. Download and save as 'credentials.json' in integrations/")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=8080)
            
            # Save token
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('fitness', 'v1', credentials=creds)
        print("✅ Google Fit authenticated successfully")
        return True
    
    def get_heart_rate(self, hours: int = 1) -> List[Dict]:
        """Get heart rate data from Google Fit."""
        if not self.service:
            return []
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Convert to nanoseconds
        start_ns = int(start_time.timestamp() * 1e9)
        end_ns = int(end_time.timestamp() * 1e9)
        
        try:
            result = self.service.users().dataSources().datasets().get(
                userId='me',
                dataSourceId='derived:com.google.heart_rate.bpm:com.google.android.gms:merge_heart_rate_bpm',
                datasetId=f"{start_ns}-{end_ns}"
            ).execute()
            
            readings = []
            for point in result.get('point', []):
                timestamp = int(point['startTimeNanos']) / 1e9
                value = point['value'][0].get('fpVal', 0)
                readings.append({
                    'timestamp': datetime.fromtimestamp(timestamp).isoformat(),
                    'heart_rate': value
                })
            
            return readings
        except Exception as e:
            print(f"Error fetching heart rate: {e}")
            return []
    
    def get_spo2(self, hours: int = 24) -> List[Dict]:
        """Get blood oxygen data from Google Fit."""
        if not self.service:
            return []
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        body = {
            "aggregateBy": [{
                "dataTypeName": "com.google.oxygen_saturation"
            }],
            "bucketByTime": {"durationMillis": 3600000},  # 1 hour buckets
            "startTimeMillis": int(start_time.timestamp() * 1000),
            "endTimeMillis": int(end_time.timestamp() * 1000)
        }
        
        try:
            result = self.service.users().dataset().aggregate(
                userId='me', body=body
            ).execute()
            
            readings = []
            for bucket in result.get('bucket', []):
                for dataset in bucket.get('dataset', []):
                    for point in dataset.get('point', []):
                        if point.get('value'):
                            readings.append({
                                'timestamp': datetime.fromtimestamp(
                                    int(bucket['startTimeMillis']) / 1000
                                ).isoformat(),
                                'spo2': point['value'][0].get('fpVal', 0) * 100
                            })
            
            return readings
        except Exception as e:
            print(f"Error fetching SpO2: {e}")
            return []
    
    def get_steps(self, hours: int = 24) -> int:
        """Get step count from Google Fit."""
        if not self.service:
            return 0
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        body = {
            "aggregateBy": [{
                "dataTypeName": "com.google.step_count.delta"
            }],
            "bucketByTime": {"durationMillis": 86400000},  # Daily
            "startTimeMillis": int(start_time.timestamp() * 1000),
            "endTimeMillis": int(end_time.timestamp() * 1000)
        }
        
        try:
            result = self.service.users().dataset().aggregate(
                userId='me', body=body
            ).execute()
            
            total_steps = 0
            for bucket in result.get('bucket', []):
                for dataset in bucket.get('dataset', []):
                    for point in dataset.get('point', []):
                        if point.get('value'):
                            total_steps += point['value'][0].get('intVal', 0)
            
            return total_steps
        except Exception as e:
            print(f"Error fetching steps: {e}")
            return 0
    
    def get_all_vitals(self, hours: int = 1) -> Dict:
        """Get all available vitals from Google Fit."""
        vitals = {
            'heart_rate': None,
            'spo2': None,
            'steps': 0,
            'timestamp': datetime.utcnow().isoformat(),
            'source': 'google_fit'
        }
        
        # Get latest heart rate
        hr_data = self.get_heart_rate(hours)
        if hr_data:
            vitals['heart_rate'] = hr_data[-1]['heart_rate']
        
        # Get latest SpO2
        spo2_data = self.get_spo2(hours)
        if spo2_data:
            vitals['spo2'] = spo2_data[-1]['spo2']
        
        # Get steps
        vitals['steps'] = self.get_steps(24)
        
        return vitals
    
    def sync_to_database(self, hours: int = 1) -> int:
        """Sync Google Fit data to AEGIS database."""
        session = SessionLocal()
        saved = 0
        
        try:
            # Get heart rate readings
            hr_readings = self.get_heart_rate(hours)
            for reading in hr_readings:
                event = HealthEvent(
                    user_id=self.user_id,
                    event_type="vitals",
                    data={
                        'heart_rate': reading['heart_rate'],
                        'source': 'google_fit'
                    },
                    timestamp=datetime.fromisoformat(reading['timestamp'])
                )
                session.add(event)
                saved += 1
            
            session.commit()
            self.last_sync = datetime.utcnow()
            print(f"✅ Synced {saved} readings from Google Fit")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Sync error: {e}")
        finally:
            session.close()
        
        return saved
    
    async def continuous_sync(self, interval_minutes: int = 5):
        """Continuously sync data from Google Fit."""
        print(f"🔄 Starting continuous sync (every {interval_minutes} min)")
        
        while True:
            try:
                vitals = self.get_all_vitals(hours=1)
                
                if vitals['heart_rate']:
                    print(f"❤️  HR: {vitals['heart_rate']} bpm | "
                          f"🫁 SpO2: {vitals.get('spo2', 'N/A')}% | "
                          f"🚶 Steps: {vitals['steps']}")
                    
                    # Save to database
                    session = SessionLocal()
                    event = HealthEvent(
                        user_id=self.user_id,
                        event_type="vitals",
                        data=vitals,
                        timestamp=datetime.utcnow()
                    )
                    session.add(event)
                    session.commit()
                    session.close()
                else:
                    print("⏳ No new data from watch")
                
            except Exception as e:
                print(f"❌ Sync error: {e}")
            
            await asyncio.sleep(interval_minutes * 60)


def setup_google_fit():
    """Interactive setup for Google Fit integration."""
    print("=" * 50)
    print("🏃 Google Fit Integration Setup")
    print("=" * 50)
    
    sync = GoogleFitSync()
    
    if sync.authenticate():
        print("\n✅ Authentication successful!")
        print("\nTesting connection...")
        
        vitals = sync.get_all_vitals(hours=24)
        print(f"\nLatest data from Google Fit:")
        print(f"  Heart Rate: {vitals.get('heart_rate', 'N/A')} bpm")
        print(f"  SpO2: {vitals.get('spo2', 'N/A')}%")
        print(f"  Steps (24h): {vitals.get('steps', 0)}")
        
        print("\n🎉 Setup complete! You can now run continuous sync:")
        print("   python google_fit.py --sync")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Google Fit Integration')
    parser.add_argument('--setup', action='store_true', help='Run initial setup')
    parser.add_argument('--sync', action='store_true', help='Start continuous sync')
    parser.add_argument('--interval', type=int, default=5, help='Sync interval in minutes')
    parser.add_argument('--user-id', type=int, default=2, help='AEGIS user ID')
    
    args = parser.parse_args()
    
    if args.setup:
        setup_google_fit()
    elif args.sync:
        sync = GoogleFitSync(user_id=args.user_id)
        if sync.authenticate():
            await sync.continuous_sync(interval_minutes=args.interval)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
