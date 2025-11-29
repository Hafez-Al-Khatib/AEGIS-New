#!/usr/bin/env python3
"""
Real-time WebSocket Server for Galaxy Watch Data

Receives live vitals from Samsung Galaxy Watch via companion app
and broadcasts to connected clients (Dashboard, MCP Server, etc.)

Usage:
    python websocket_server.py --port 8765

Connect from watch companion app:
    ws://your-server:8765/watch

Connect from dashboard:
    ws://your-server:8765/dashboard
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import websockets
    from websockets.server import serve
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("websockets not installed. Run: pip install websockets")

from database import SessionLocal
from models import HealthEvent, Alert

# Connected clients
WATCH_CLIENTS = set()
DASHBOARD_CLIENTS = set()

# Real-time vitals cache
CURRENT_VITALS = {
    "heart_rate": None,
    "spo2": None,
    "stress_level": None,
    "steps": 0,
    "systolic_bp": None,
    "diastolic_bp": None,
    "last_update": None,
    "watch_connected": False
}

# Alert thresholds
THRESHOLDS = {
    "heart_rate": {"low": 40, "high": 150},
    "spo2": {"low": 90},
    "systolic_bp": {"low": 80, "high": 180}
}


async def check_and_alert(vitals: dict, user_id: int = 2):
    """Check vitals and create alerts if needed."""
    alerts = []
    session = SessionLocal()
    
    try:
        hr = vitals.get('heart_rate')
        if hr:
            if hr < THRESHOLDS['heart_rate']['low']:
                alerts.append(f"⚠️ BRADYCARDIA: Heart rate {hr} bpm is critically low!")
            elif hr > THRESHOLDS['heart_rate']['high']:
                alerts.append(f"⚠️ TACHYCARDIA: Heart rate {hr} bpm is critically high!")
        
        spo2 = vitals.get('spo2')
        if spo2 and spo2 < THRESHOLDS['spo2']['low']:
            alerts.append(f"⚠️ HYPOXEMIA: Blood oxygen {spo2}% is critically low!")
        
        sbp = vitals.get('systolic_bp')
        if sbp:
            if sbp > THRESHOLDS['systolic_bp']['high']:
                alerts.append(f"⚠️ HYPERTENSIVE CRISIS: BP {sbp} mmHg!")
            elif sbp < THRESHOLDS['systolic_bp']['low']:
                alerts.append(f"⚠️ HYPOTENSION: BP {sbp} mmHg is low!")
        
        # Save alerts to database
        for msg in alerts:
            db_alert = Alert(
                user_id=user_id,
                message=msg,
                severity="HIGH"
            )
            session.add(db_alert)
        
        if alerts:
            session.commit()
            print(f"[ALERT] Created {len(alerts)} alerts")
            
    finally:
        session.close()
    
    return alerts


async def save_vitals(vitals: dict, user_id: int = 2):
    """Save vitals to database."""
    session = SessionLocal()
    try:
        # Remove metadata fields
        data = {k: v for k, v in vitals.items() 
                if k not in ['last_update', 'watch_connected'] and v is not None}
        data['source'] = 'galaxy_watch_realtime'
        
        event = HealthEvent(
            user_id=user_id,
            event_type="vitals",
            data=data,
            timestamp=datetime.utcnow()
        )
        session.add(event)
        session.commit()
        print(f"[DB] Saved vitals: HR={data.get('heart_rate')}, SpO2={data.get('spo2')}")
    except Exception as e:
        print(f"[DB ERROR] {e}")
    finally:
        session.close()


async def broadcast_to_dashboards(message: dict):
    """Send data to all connected dashboard clients."""
    if DASHBOARD_CLIENTS:
        msg = json.dumps(message)
        await asyncio.gather(
            *[client.send(msg) for client in DASHBOARD_CLIENTS],
            return_exceptions=True
        )


async def handle_watch(websocket, path):
    """Handle incoming connection from Galaxy Watch companion app."""
    WATCH_CLIENTS.add(websocket)
    CURRENT_VITALS['watch_connected'] = True
    print(f"[WATCH] Connected: {websocket.remote_address}")
    
    # Notify dashboards
    await broadcast_to_dashboards({
        "type": "watch_status",
        "connected": True,
        "timestamp": datetime.now().isoformat()
    })
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                print(f"[WATCH] Received: {data}")
                
                # Update real-time cache
                CURRENT_VITALS.update(data)
                CURRENT_VITALS['last_update'] = datetime.now().isoformat()
                
                # Check for alerts
                alerts = await check_and_alert(data)
                
                # Save to database (batch every 5 minutes or on significant change)
                await save_vitals(data)
                
                # Broadcast to dashboards
                await broadcast_to_dashboards({
                    "type": "vitals_update",
                    "data": CURRENT_VITALS,
                    "alerts": alerts
                })
                
                # Acknowledge receipt
                await websocket.send(json.dumps({
                    "status": "received",
                    "alerts": alerts
                }))
                
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "Invalid JSON"}))
                
    except websockets.exceptions.ConnectionClosed:
        print(f"[WATCH] Disconnected: {websocket.remote_address}")
    finally:
        WATCH_CLIENTS.discard(websocket)
        CURRENT_VITALS['watch_connected'] = False
        await broadcast_to_dashboards({
            "type": "watch_status",
            "connected": False,
            "timestamp": datetime.now().isoformat()
        })


async def handle_dashboard(websocket, path):
    """Handle dashboard client connections."""
    DASHBOARD_CLIENTS.add(websocket)
    print(f"[DASHBOARD] Connected: {websocket.remote_address}")
    
    # Send current state
    await websocket.send(json.dumps({
        "type": "initial_state",
        "data": CURRENT_VITALS
    }))
    
    try:
        async for message in websocket:
            # Dashboard can request data
            try:
                req = json.loads(message)
                if req.get('action') == 'get_vitals':
                    await websocket.send(json.dumps({
                        "type": "vitals_update",
                        "data": CURRENT_VITALS
                    }))
            except:
                pass
                
    except websockets.exceptions.ConnectionClosed:
        print(f"[DASHBOARD] Disconnected: {websocket.remote_address}")
    finally:
        DASHBOARD_CLIENTS.discard(websocket)


async def router(websocket, path):
    """Route connections based on path."""
    if path == "/watch":
        await handle_watch(websocket, path)
    elif path == "/dashboard":
        await handle_dashboard(websocket, path)
    else:
        # Default to watch handler
        await handle_watch(websocket, path)


async def main():
    """Start the WebSocket server."""
    if not WEBSOCKETS_AVAILABLE:
        print("Please install websockets: pip install websockets")
        return
    
    port = int(os.getenv("WS_PORT", 8765))
    
    print("=" * 50)
    print("🏥 AEGIS Galaxy Watch Real-time Server")
    print("=" * 50)
    print(f"\n📡 WebSocket server starting on port {port}")
    print(f"\n   Watch endpoint:     ws://localhost:{port}/watch")
    print(f"   Dashboard endpoint: ws://localhost:{port}/dashboard")
    print("\n   Waiting for connections...")
    print("-" * 50)
    
    async with serve(router, "0.0.0.0", port):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
