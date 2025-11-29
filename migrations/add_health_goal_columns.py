"""
Migration: Add missing columns to health_goals table

Run this script to add the new HealthGoal columns to your database.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text

MIGRATION_SQL = """
-- Add missing columns to health_goals table
ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS category VARCHAR;
ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS priority VARCHAR DEFAULT 'medium';
ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS rationale VARCHAR;
ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS condition_link VARCHAR;
ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0;
ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS habitica_task_id VARCHAR;
ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
"""

def run_migration():
    print("🔄 Running migration: Add health_goal columns...")
    
    with engine.connect() as conn:
        # Split into individual statements for PostgreSQL
        statements = [
            "ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS category VARCHAR",
            "ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS priority VARCHAR DEFAULT 'medium'",
            "ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS rationale VARCHAR",
            "ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS condition_link VARCHAR",
            "ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0",
            "ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS habitica_task_id VARCHAR",
            "ALTER TABLE health_goals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
        ]
        
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                print(f"  ✅ {stmt[:50]}...")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"  ⏭️ Column already exists, skipping...")
                else:
                    print(f"  ❌ Error: {e}")
        
        conn.commit()
    
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    run_migration()
