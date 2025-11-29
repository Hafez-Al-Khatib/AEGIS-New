"""
Migration: Add emergency contact and call log tables

Run this script to add emergency contact management tables.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text

def run_migration():
    print("🔄 Running migration: Add emergency tables...")
    
    with engine.connect() as conn:
        # Create emergency_contacts table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS emergency_contacts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    name VARCHAR NOT NULL,
                    relationship VARCHAR,
                    phone_number VARCHAR NOT NULL,
                    email VARCHAR,
                    priority INTEGER DEFAULT 1,
                    is_active VARCHAR DEFAULT 'true',
                    notify_on_critical VARCHAR DEFAULT 'true',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            print("  ✅ Created emergency_contacts table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  ⏭️ emergency_contacts table already exists")
            else:
                print(f"  ❌ Error: {e}")
        
        # Create emergency_call_logs table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS emergency_call_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    contact_id INTEGER REFERENCES emergency_contacts(id),
                    trigger_type VARCHAR,
                    trigger_details JSONB,
                    call_sid VARCHAR,
                    status VARCHAR,
                    duration_seconds INTEGER,
                    recording_url VARCHAR,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            print("  ✅ Created emergency_call_logs table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  ⏭️ emergency_call_logs table already exists")
            else:
                print(f"  ❌ Error: {e}")
        
        # Create indexes
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_emergency_contacts_user ON emergency_contacts(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_emergency_call_logs_user ON emergency_call_logs(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_emergency_call_logs_sid ON emergency_call_logs(call_sid)"))
            print("  ✅ Created indexes")
        except Exception as e:
            print(f"  ⚠️ Index creation: {e}")
        
        conn.commit()
    
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    run_migration()
