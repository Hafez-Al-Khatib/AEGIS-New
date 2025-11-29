"""
Twilio Emergency Call Integration for AEGIS

This module handles emergency phone calls to designated contacts when:
1. Critical vital signs are detected
2. User requests emergency assistance
3. Agent detects emergency language/conditions

Setup:
1. Create a Twilio account at https://www.twilio.com
2. Get your Account SID and Auth Token
3. Purchase a phone number with voice capability
4. Set environment variables:
   - TWILIO_ACCOUNT_SID
   - TWILIO_AUTH_TOKEN
   - TWILIO_PHONE_NUMBER
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime

# Twilio imports
try:
    from twilio.rest import Client
    from twilio.twiml.voice_response import VoiceResponse
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("[WARNING] Twilio not installed. Run: pip install twilio")

from database import SessionLocal
import models

# Configuration from environment
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
AEGIS_BASE_URL = os.getenv("AEGIS_BASE_URL", "http://localhost:8000")

# Critical thresholds for auto-triggering
CRITICAL_THRESHOLDS = {
    "heart_rate": {"min": 40, "max": 150},
    "spo2": {"min": 88},
    "systolic_bp": {"min": 80, "max": 180},
    "diastolic_bp": {"min": 50, "max": 120},
    "temperature": {"min": 35.0, "max": 39.5},
    "respiratory_rate": {"min": 8, "max": 30}
}

# Sustained critical settings
SUSTAINED_CRITICAL_COUNT = 3  # Number of consecutive critical readings required
SUSTAINED_CRITICAL_WINDOW_MINUTES = 5  # Time window to check for sustained readings


def is_twilio_configured() -> bool:
    """Check if Twilio is properly configured."""
    return all([
        TWILIO_AVAILABLE,
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN,
        TWILIO_PHONE_NUMBER
    ])


def get_twilio_client():
    """Get Twilio client instance."""
    if not is_twilio_configured():
        return None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def check_critical_vitals(vitals: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check if any vital signs exceed critical thresholds.
    Returns list of critical readings with details.
    """
    critical_alerts = []
    
    for vital_name, thresholds in CRITICAL_THRESHOLDS.items():
        value = vitals.get(vital_name)
        if value is None:
            continue
            
        if "min" in thresholds and value < thresholds["min"]:
            critical_alerts.append({
                "vital": vital_name,
                "value": value,
                "threshold": f"< {thresholds['min']}",
                "severity": "CRITICAL",
                "message": f"{vital_name.replace('_', ' ').title()} critically low: {value}"
            })
        
        if "max" in thresholds and value > thresholds["max"]:
            critical_alerts.append({
                "vital": vital_name,
                "value": value,
                "threshold": f"> {thresholds['max']}",
                "severity": "CRITICAL",
                "message": f"{vital_name.replace('_', ' ').title()} critically high: {value}"
            })
    
    return critical_alerts


def check_sustained_critical(user_id: int, current_vitals: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """
    Check if vitals have been critical for a sustained period.
    Only triggers emergency if SUSTAINED_CRITICAL_COUNT readings are critical
    within SUSTAINED_CRITICAL_WINDOW_MINUTES.
    
    Returns emergency info if sustained critical detected, None otherwise.
    """
    from datetime import datetime, timedelta
    
    session = SessionLocal()
    try:
        # Get recent vitals within the window
        window_start = datetime.now() - timedelta(minutes=SUSTAINED_CRITICAL_WINDOW_MINUTES)
        
        recent_events = session.query(models.HealthEvent).filter(
            models.HealthEvent.user_id == user_id,
            models.HealthEvent.event_type == "vitals",
            models.HealthEvent.timestamp >= window_start
        ).order_by(models.HealthEvent.timestamp.desc()).limit(10).all()
        
        if len(recent_events) < SUSTAINED_CRITICAL_COUNT:
            # Not enough readings yet
            return None
        
        # Check last N readings for critical values
        critical_count = 0
        critical_details = []
        
        for event in recent_events[:SUSTAINED_CRITICAL_COUNT]:
            vitals = event.data or {}
            alerts = check_critical_vitals(vitals)
            if alerts:
                critical_count += 1
                critical_details.extend(alerts)
        
        if critical_count >= SUSTAINED_CRITICAL_COUNT:
            # Sustained critical detected!
            print(f"🚨 [SUSTAINED CRITICAL] User {user_id}: {critical_count} consecutive critical readings")
            
            # Check if we already called in the last 30 minutes (prevent spam)
            thirty_min_ago = datetime.now() - timedelta(minutes=30)
            recent_call = session.query(models.EmergencyCallLog).filter(
                models.EmergencyCallLog.user_id == user_id,
                models.EmergencyCallLog.timestamp >= thirty_min_ago,
                models.EmergencyCallLog.trigger_type == "vital_alert"
            ).first()
            
            if recent_call:
                print(f"    ⏭️ Skipping - already called {recent_call.timestamp}")
                return None
            
            # Get the most critical reading
            latest_vitals = recent_events[0].data if recent_events else current_vitals
            
            return {
                "trigger": True,
                "reason": f"Sustained critical vitals detected ({critical_count} readings)",
                "details": critical_details[:3],  # Top 3 alerts
                "vitals": latest_vitals,
                "readings_count": critical_count
            }
        
        return None
        
    except Exception as e:
        print(f"[SUSTAINED CHECK ERROR] {e}")
        return None
    finally:
        session.close()


def auto_trigger_emergency_if_critical(user_id: int, vitals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Called after each vitals reading. Checks for sustained critical and auto-triggers emergency.
    
    Returns call result if triggered, None otherwise.
    """
    # First check if this reading is critical
    current_alerts = check_critical_vitals(vitals)
    if not current_alerts:
        return None  # Current reading is fine, no need to check history
    
    # Check for sustained critical
    sustained = check_sustained_critical(user_id, vitals)
    
    if sustained and sustained.get("trigger"):
        print(f"🚨🚨🚨 [AUTO-EMERGENCY] Triggering emergency call for user {user_id}")
        
        # Build reason message
        alert_msgs = [d.get("message", "") for d in sustained.get("details", [])]
        reason = f"CRITICAL VITALS ALERT: {'; '.join(alert_msgs[:2])}"
        
        # Make the call
        result = make_emergency_call(
            user_id=user_id,
            reason=reason,
            trigger_type="vital_alert",
            vitals=vitals
        )
        
        return result
    
    return None


def get_emergency_contacts(user_id: int, session=None) -> List[models.EmergencyContact]:
    """Get active emergency contacts for a user, ordered by priority."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True
    
    try:
        contacts = session.query(models.EmergencyContact).filter(
            models.EmergencyContact.user_id == user_id,
            models.EmergencyContact.is_active == "true"
        ).order_by(models.EmergencyContact.priority).all()
        return contacts
    finally:
        if close_session:
            session.close()


def generate_emergency_twiml(
    patient_name: str,
    reason: str,
    vitals_info: str = "",
    callback_number: str = None
) -> str:
    """
    Generate TwiML for the emergency call.
    Uses text-to-speech to deliver the emergency message.
    """
    response = VoiceResponse()
    
    # Urgent tone
    response.say(
        "This is an urgent health alert from Aegis Health System.",
        voice="alice",
        language="en-US"
    )
    
    response.pause(length=1)
    
    # Patient info
    response.say(
        f"Patient {patient_name} requires immediate attention.",
        voice="alice"
    )
    
    response.pause(length=1)
    
    # Reason
    response.say(
        f"Alert reason: {reason}",
        voice="alice"
    )
    
    if vitals_info:
        response.pause(length=1)
        response.say(
            f"Current vital signs: {vitals_info}",
            voice="alice"
        )
    
    response.pause(length=2)
    
    # Instructions
    response.say(
        "Please check on the patient immediately. "
        "If this is a life-threatening emergency, call emergency services.",
        voice="alice"
    )
    
    # Repeat key info
    response.pause(length=1)
    response.say(
        "Repeating: This is an urgent health alert. "
        f"Patient {patient_name} requires immediate attention. "
        f"Reason: {reason}",
        voice="alice"
    )
    
    # Option to acknowledge
    response.say(
        "Press 1 to confirm you received this message. Press 2 to hear this message again.",
        voice="alice"
    )
    
    # Gather response
    gather = response.gather(num_digits=1, action=f"{AEGIS_BASE_URL}/emergency/callback", method="POST")
    gather.say("Press 1 to confirm, or press 2 to repeat.", voice="alice")
    
    return str(response)


def make_emergency_call(
    user_id: int,
    reason: str,
    trigger_type: str = "agent_detected",
    vitals: Dict[str, Any] = None,
    contact_id: int = None
) -> Dict[str, Any]:
    """
    Make an emergency phone call to user's emergency contacts.
    
    Args:
        user_id: The patient's user ID
        reason: Why the call is being made
        trigger_type: "vital_alert", "user_request", or "agent_detected"
        vitals: Current vital signs (optional)
        contact_id: Specific contact to call (optional, otherwise calls by priority)
    
    Returns:
        Dict with call status and details
    """
    print(f"\n🚨 [EMERGENCY] Initiating emergency call for user {user_id}")
    print(f"    Reason: {reason}")
    print(f"    Trigger: {trigger_type}")
    
    if not is_twilio_configured():
        error_msg = "Twilio not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER"
        print(f"    ❌ {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "configured": False
        }
    
    session = SessionLocal()
    try:
        # Get user info
        user = session.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return {"success": False, "error": "User not found"}
        
        patient_name = user.email.split("@")[0].title()  # Use email prefix as name
        
        # Get emergency contacts
        if contact_id:
            contacts = [session.query(models.EmergencyContact).filter(
                models.EmergencyContact.id == contact_id
            ).first()]
        else:
            contacts = get_emergency_contacts(user_id, session)
        
        if not contacts or not contacts[0]:
            error_msg = "No emergency contacts configured for this user"
            print(f"    ⚠️ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "action_required": "Please add emergency contacts in settings"
            }
        
        # Format vitals info
        vitals_info = ""
        if vitals:
            vitals_parts = []
            if vitals.get("heart_rate"):
                vitals_parts.append(f"heart rate {vitals['heart_rate']} bpm")
            if vitals.get("spo2"):
                vitals_parts.append(f"oxygen saturation {vitals['spo2']}%")
            if vitals.get("systolic_bp") and vitals.get("diastolic_bp"):
                vitals_parts.append(f"blood pressure {vitals['systolic_bp']} over {vitals['diastolic_bp']}")
            vitals_info = ", ".join(vitals_parts)
        
        # Get Twilio client
        client = get_twilio_client()
        
        call_results = []
        
        # Call each contact (up to 3)
        for contact in contacts[:3]:
            print(f"    📞 Calling {contact.name} ({contact.relationship}) at {contact.phone_number}")
            
            try:
                # Generate TwiML
                twiml = generate_emergency_twiml(
                    patient_name=patient_name,
                    reason=reason,
                    vitals_info=vitals_info
                )
                
                # Make the call
                call = client.calls.create(
                    to=contact.phone_number,
                    from_=TWILIO_PHONE_NUMBER,
                    twiml=twiml,
                    status_callback=f"{AEGIS_BASE_URL}/emergency/status",
                    status_callback_event=["initiated", "ringing", "answered", "completed"],
                    status_callback_method="POST",
                    timeout=30,  # Ring for 30 seconds
                    record=True  # Record for documentation
                )
                
                # Log the call
                call_log = models.EmergencyCallLog(
                    user_id=user_id,
                    contact_id=contact.id,
                    trigger_type=trigger_type,
                    trigger_details={
                        "reason": reason,
                        "vitals": vitals
                    },
                    call_sid=call.sid,
                    status="initiated"
                )
                session.add(call_log)
                session.commit()
                
                call_results.append({
                    "contact_name": contact.name,
                    "phone": contact.phone_number,
                    "call_sid": call.sid,
                    "status": "initiated"
                })
                
                print(f"    ✅ Call initiated: {call.sid}")
                
            except Exception as e:
                print(f"    ❌ Failed to call {contact.name}: {e}")
                call_results.append({
                    "contact_name": contact.name,
                    "phone": contact.phone_number,
                    "error": str(e)
                })
        
        return {
            "success": True,
            "calls": call_results,
            "patient": patient_name,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"    ❌ Emergency call failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def send_emergency_sms(
    user_id: int,
    message: str,
    contact_id: int = None
) -> Dict[str, Any]:
    """
    Send emergency SMS to user's emergency contacts.
    Useful as a backup when calls don't connect.
    """
    if not is_twilio_configured():
        return {"success": False, "error": "Twilio not configured"}
    
    session = SessionLocal()
    try:
        contacts = get_emergency_contacts(user_id, session) if not contact_id else [
            session.query(models.EmergencyContact).filter(
                models.EmergencyContact.id == contact_id
            ).first()
        ]
        
        if not contacts:
            return {"success": False, "error": "No emergency contacts"}
        
        client = get_twilio_client()
        results = []
        
        for contact in contacts[:3]:
            try:
                sms = client.messages.create(
                    to=contact.phone_number,
                    from_=TWILIO_PHONE_NUMBER,
                    body=f"🚨 AEGIS HEALTH ALERT: {message}"
                )
                results.append({
                    "contact": contact.name,
                    "sid": sms.sid,
                    "status": "sent"
                })
            except Exception as e:
                results.append({
                    "contact": contact.name,
                    "error": str(e)
                })
        
        return {"success": True, "messages": results}
        
    finally:
        session.close()


# ========== EMERGENCY DETECTION KEYWORDS ==========

EMERGENCY_KEYWORDS = [
    # Cardiac
    "heart attack", "chest pain", "can't breathe", "difficulty breathing",
    "crushing pain", "pain in my chest", "arm pain spreading", "jaw pain",
    "palpitations", "irregular heartbeat", "heart racing",
    
    # Stroke
    "stroke", "face drooping", "can't speak", "slurred speech",
    "numbness", "one side weak", "sudden confusion", "vision problems",
    
    # Respiratory
    "choking", "can't get air", "gasping", "suffocating",
    "severe asthma", "anaphylaxis", "throat closing",
    
    # Other emergencies
    "unconscious", "passed out", "fainted", "seizure", "convulsing",
    "severe bleeding", "bleeding heavily", "overdose", "poisoning",
    "severe allergic", "suicidal", "want to die", "hurt myself",
    "falling", "fell down", "head injury", "broken bone",
    
    # Direct requests
    "call emergency", "call ambulance", "call 911", "call help",
    "need ambulance", "get help", "emergency contact", "call my",
    "dying", "i'm dying", "help me", "urgent help"
]


def detect_emergency_in_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Detect emergency keywords/phrases in user message.
    Returns emergency details if detected, None otherwise.
    """
    text_lower = text.lower()
    
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text_lower:
            # Categorize the emergency
            category = "unknown"
            if any(w in keyword for w in ["heart", "chest", "cardiac", "palpitations"]):
                category = "cardiac"
            elif any(w in keyword for w in ["stroke", "face", "speech", "numbness"]):
                category = "stroke"
            elif any(w in keyword for w in ["breath", "chok", "air", "throat", "asthma"]):
                category = "respiratory"
            elif any(w in keyword for w in ["suicidal", "die", "hurt myself"]):
                category = "mental_health_crisis"
            elif any(w in keyword for w in ["call", "ambulance", "911", "emergency"]):
                category = "assistance_request"
            
            return {
                "detected": True,
                "keyword": keyword,
                "category": category,
                "severity": "critical" if category in ["cardiac", "stroke", "respiratory"] else "high",
                "original_text": text[:200]
            }
    
    return None
