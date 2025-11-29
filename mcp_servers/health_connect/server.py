#!/usr/bin/env python3
"""
AEGIS Health Connect MCP Server

A Model Context Protocol server that provides real-time health data
from Samsung Galaxy Watch and other wearables.

Features:
- Real-time vitals monitoring
- Historical health trends
- Alert generation for abnormal values
- Integration with Samsung Health exports
- WebSocket support for live updates

Usage:
    python server.py --port 8765
    
Or via MCP config in your IDE.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        Tool,
        TextContent,
        Resource,
        ResourceTemplate,
    )
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("[Health Connect MCP] Warning: mcp package not installed. Running in standalone mode.")

# Configuration
DB_PATH = Path(__file__).parent.parent.parent / "aegis.db"
WATCH_DATA_DIR = Path(__file__).parent / "watch_data"
WATCH_DATA_DIR.mkdir(exist_ok=True)

# In-memory cache for real-time data
REALTIME_CACHE = {
    "heart_rate": None,
    "spo2": None,
    "stress": None,
    "steps": 0,
    "last_update": None
}

# Alert thresholds
THRESHOLDS = {
    "heart_rate_low": 40,
    "heart_rate_high": 150,
    "spo2_low": 90,
    "bp_systolic_high": 180,
    "bp_systolic_low": 80,
    "stress_high": 80
}


def get_db_connection():
    """Get SQLite database connection."""
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH))


def get_latest_vitals(user_id: int = None) -> dict:
    """Get the most recent vitals from database."""
    conn = get_db_connection()
    if not conn:
        return {"error": "Database not found"}
    
    try:
        cursor = conn.cursor()
        
        # Get latest vitals event
        if user_id:
            cursor.execute("""
                SELECT data, timestamp FROM health_events 
                WHERE event_type = 'vitals' AND user_id = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT data, timestamp FROM health_events 
                WHERE event_type = 'vitals'
                ORDER BY timestamp DESC LIMIT 1
            """)
        
        row = cursor.fetchone()
        if row:
            data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            data['timestamp'] = row[1]
            return data
        
        return {"message": "No vitals data found"}
    finally:
        conn.close()


def get_vitals_trend(user_id: int = None, hours: int = 24) -> dict:
    """Get vitals trend over specified hours."""
    conn = get_db_connection()
    if not conn:
        return {"error": "Database not found"}
    
    try:
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        if user_id:
            cursor.execute("""
                SELECT data, timestamp FROM health_events 
                WHERE event_type = 'vitals' AND user_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (user_id, cutoff))
        else:
            cursor.execute("""
                SELECT data, timestamp FROM health_events 
                WHERE event_type = 'vitals' AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (cutoff,))
        
        rows = cursor.fetchall()
        
        heart_rates = []
        spo2_values = []
        timestamps = []
        
        for row in rows:
            data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            if data.get('heart_rate'):
                heart_rates.append(data['heart_rate'])
            if data.get('spo2'):
                spo2_values.append(data['spo2'])
            timestamps.append(row[1])
        
        return {
            "period_hours": hours,
            "data_points": len(rows),
            "heart_rate": {
                "avg": round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else None,
                "min": min(heart_rates) if heart_rates else None,
                "max": max(heart_rates) if heart_rates else None,
                "values": heart_rates[-20:]  # Last 20 readings
            },
            "spo2": {
                "avg": round(sum(spo2_values) / len(spo2_values), 1) if spo2_values else None,
                "min": min(spo2_values) if spo2_values else None,
                "max": max(spo2_values) if spo2_values else None,
            },
            "first_reading": timestamps[0] if timestamps else None,
            "last_reading": timestamps[-1] if timestamps else None
        }
    finally:
        conn.close()


def check_vitals_alerts(vitals: dict) -> list:
    """Check vitals against thresholds and return alerts."""
    alerts = []
    
    hr = vitals.get('heart_rate')
    if hr:
        if hr < THRESHOLDS['heart_rate_low']:
            alerts.append({
                "type": "CRITICAL",
                "metric": "heart_rate",
                "value": hr,
                "message": f"Bradycardia detected: Heart rate {hr} bpm is dangerously low"
            })
        elif hr > THRESHOLDS['heart_rate_high']:
            alerts.append({
                "type": "CRITICAL", 
                "metric": "heart_rate",
                "value": hr,
                "message": f"Tachycardia detected: Heart rate {hr} bpm is dangerously high"
            })
    
    spo2 = vitals.get('spo2')
    if spo2 and spo2 < THRESHOLDS['spo2_low']:
        alerts.append({
            "type": "CRITICAL",
            "metric": "spo2",
            "value": spo2,
            "message": f"Hypoxemia detected: Blood oxygen {spo2}% is critically low"
        })
    
    systolic = vitals.get('systolic_bp')
    if systolic:
        if systolic > THRESHOLDS['bp_systolic_high']:
            alerts.append({
                "type": "WARNING",
                "metric": "blood_pressure",
                "value": systolic,
                "message": f"Hypertensive crisis: Blood pressure {systolic} mmHg requires attention"
            })
        elif systolic < THRESHOLDS['bp_systolic_low']:
            alerts.append({
                "type": "WARNING",
                "metric": "blood_pressure", 
                "value": systolic,
                "message": f"Hypotension: Blood pressure {systolic} mmHg is low"
            })
    
    stress = vitals.get('stress_level')
    if stress and stress > THRESHOLDS['stress_high']:
        alerts.append({
            "type": "INFO",
            "metric": "stress",
            "value": stress,
            "message": f"High stress level detected: {stress}/100. Consider relaxation techniques."
        })
    
    return alerts


def get_health_insights(user_id: int = None) -> dict:
    """Generate health insights based on recent data."""
    trend = get_vitals_trend(user_id, hours=168)  # 7 days
    latest = get_latest_vitals(user_id)
    
    insights = []
    
    # Heart rate insights
    if trend.get('heart_rate', {}).get('avg'):
        avg_hr = trend['heart_rate']['avg']
        if avg_hr < 60:
            insights.append("Your average heart rate indicates excellent cardiovascular fitness.")
        elif avg_hr > 100:
            insights.append("Your resting heart rate is elevated. Consider stress management and cardio exercise.")
    
    # SpO2 insights
    if trend.get('spo2', {}).get('avg'):
        avg_spo2 = trend['spo2']['avg']
        if avg_spo2 >= 95:
            insights.append("Your blood oxygen levels are healthy and consistent.")
        elif avg_spo2 < 95:
            insights.append("Your blood oxygen has been slightly below optimal. Monitor closely.")
    
    # Data consistency
    if trend.get('data_points', 0) < 10:
        insights.append("Limited data available. Wear your watch more consistently for better insights.")
    
    return {
        "period": "7 days",
        "insights": insights,
        "latest_vitals": latest,
        "trend_summary": {
            "avg_heart_rate": trend.get('heart_rate', {}).get('avg'),
            "avg_spo2": trend.get('spo2', {}).get('avg'),
            "total_readings": trend.get('data_points', 0)
        }
    }


def update_realtime_cache(data: dict):
    """Update the real-time cache with new data."""
    global REALTIME_CACHE
    REALTIME_CACHE.update(data)
    REALTIME_CACHE['last_update'] = datetime.now().isoformat()


# ============== MCP SERVER ==============

if MCP_AVAILABLE:
    server = Server("health-connect")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available health monitoring tools."""
        return [
            Tool(
                name="get_current_vitals",
                description="Get the most recent vital signs from Samsung Galaxy Watch (heart rate, SpO2, blood pressure, stress)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "User ID (optional)"}
                    }
                }
            ),
            Tool(
                name="get_vitals_trend",
                description="Get vital signs trend over a time period (averages, min/max, data points)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "hours": {"type": "integer", "default": 24, "description": "Hours to look back"},
                        "user_id": {"type": "integer", "description": "User ID (optional)"}
                    }
                }
            ),
            Tool(
                name="check_health_alerts",
                description="Check current vitals for any health alerts or abnormal values",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "User ID (optional)"}
                    }
                }
            ),
            Tool(
                name="get_health_insights",
                description="Get AI-generated health insights based on watch data trends",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "User ID (optional)"}
                    }
                }
            ),
            Tool(
                name="log_watch_reading",
                description="Log a new reading from the Galaxy Watch",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "heart_rate": {"type": "number"},
                        "spo2": {"type": "number"},
                        "stress_level": {"type": "integer"},
                        "steps": {"type": "integer"},
                        "systolic_bp": {"type": "integer"},
                        "diastolic_bp": {"type": "integer"}
                    }
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        
        if name == "get_current_vitals":
            result = get_latest_vitals(arguments.get('user_id'))
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        
        elif name == "get_vitals_trend":
            result = get_vitals_trend(
                arguments.get('user_id'),
                arguments.get('hours', 24)
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        
        elif name == "check_health_alerts":
            vitals = get_latest_vitals(arguments.get('user_id'))
            alerts = check_vitals_alerts(vitals)
            result = {
                "vitals": vitals,
                "alerts": alerts,
                "status": "ALERT" if any(a['type'] == 'CRITICAL' for a in alerts) else "OK"
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        
        elif name == "get_health_insights":
            result = get_health_insights(arguments.get('user_id'))
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        
        elif name == "log_watch_reading":
            update_realtime_cache(arguments)
            return [TextContent(type="text", text=json.dumps({
                "status": "logged",
                "data": arguments,
                "timestamp": datetime.now().isoformat()
            }, indent=2))]
        
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available health data resources."""
        return [
            Resource(
                uri="health://vitals/current",
                name="Current Vitals",
                description="Real-time vital signs from Galaxy Watch",
                mimeType="application/json"
            ),
            Resource(
                uri="health://vitals/trend/24h",
                name="24-Hour Trend",
                description="Vital signs trend over last 24 hours",
                mimeType="application/json"
            ),
            Resource(
                uri="health://insights",
                name="Health Insights",
                description="AI-generated health insights",
                mimeType="application/json"
            )
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read health data resources."""
        if uri == "health://vitals/current":
            return json.dumps(get_latest_vitals(), indent=2, default=str)
        elif uri == "health://vitals/trend/24h":
            return json.dumps(get_vitals_trend(hours=24), indent=2, default=str)
        elif uri == "health://insights":
            return json.dumps(get_health_insights(), indent=2, default=str)
        return json.dumps({"error": f"Unknown resource: {uri}"})


async def main():
    """Run the MCP server."""
    if MCP_AVAILABLE:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    else:
        # Standalone mode - just print capabilities
        print("=" * 50)
        print("AEGIS Health Connect Server (Standalone Mode)")
        print("=" * 50)
        print("\nAvailable functions:")
        print("  - get_latest_vitals(user_id)")
        print("  - get_vitals_trend(user_id, hours)")
        print("  - check_vitals_alerts(vitals)")
        print("  - get_health_insights(user_id)")
        print("\nTo enable MCP mode, install: pip install mcp")
        print("\nTesting with current database...")
        print(json.dumps(get_latest_vitals(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
