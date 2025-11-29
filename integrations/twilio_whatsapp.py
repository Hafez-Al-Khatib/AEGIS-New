"""
AEGIS Twilio WhatsApp Integration

Enables conversational appointment booking with physicians via WhatsApp.
Uses Twilio's WhatsApp Business API for two-way messaging.

Features:
- Send booking requests to physician offices
- Handle incoming responses via webhooks
- Manage conversation state for multi-turn booking
- Template messages for common booking scenarios

Setup:
1. Enable WhatsApp in Twilio Console
2. Configure webhook URL for incoming messages
3. Set TWILIO_WHATSAPP_NUMBER in environment
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from database import SessionLocal
import models

# ============================================================================
# Configuration
# ============================================================================

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")  # Format: whatsapp:+14155238886

# Base URL for webhooks (use ngrok for local dev)
AEGIS_BASE_URL = os.getenv("AEGIS_BASE_URL", "http://localhost:8000")


def is_whatsapp_configured() -> bool:
    """Check if WhatsApp is properly configured."""
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_NUMBER)


def get_twilio_client() -> Optional[Client]:
    """Get Twilio client if configured."""
    if not is_whatsapp_configured():
        return None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# ============================================================================
# Conversation State Management
# ============================================================================

class BookingState(Enum):
    """States for the booking conversation flow."""
    INITIATED = "initiated"           # Initial booking request sent
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # Waiting for office response
    AWAITING_TIME_OPTIONS = "awaiting_time_options"  # Asked for available times
    TIME_PROPOSED = "time_proposed"   # We proposed a time
    CONFIRMED = "confirmed"           # Appointment confirmed
    REJECTED = "rejected"             # Booking rejected/unavailable
    EXPIRED = "expired"               # Conversation timed out


class WhatsAppBookingSession:
    """Manages a WhatsApp booking conversation session."""
    
    # In-memory store (use Redis in production)
    _sessions: Dict[str, Dict] = {}
    
    @classmethod
    def create(
        cls,
        user_id: int,
        physician_phone: str,
        physician_name: str,
        patient_name: str,
        preferred_time: str,
        reason: str = "General checkup"
    ) -> str:
        """Create a new booking session."""
        session_id = f"booking_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        cls._sessions[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "physician_phone": physician_phone,
            "physician_name": physician_name,
            "patient_name": patient_name,
            "preferred_time": preferred_time,
            "reason": reason,
            "state": BookingState.INITIATED.value,
            "created_at": datetime.now().isoformat(),
            "messages": [],
            "confirmed_time": None
        }
        
        return session_id
    
    @classmethod
    def get(cls, session_id: str) -> Optional[Dict]:
        """Get session by ID."""
        return cls._sessions.get(session_id)
    
    @classmethod
    def get_by_phone(cls, phone: str) -> Optional[Dict]:
        """Get active session by physician phone number."""
        # Normalize phone format
        phone_normalized = phone.replace("whatsapp:", "").strip()
        
        for session in cls._sessions.values():
            if session["physician_phone"].replace("+", "").strip() == phone_normalized.replace("+", "").strip():
                if session["state"] not in [BookingState.CONFIRMED.value, BookingState.REJECTED.value, BookingState.EXPIRED.value]:
                    return session
        return None
    
    @classmethod
    def update_state(cls, session_id: str, state: BookingState, **kwargs):
        """Update session state."""
        if session_id in cls._sessions:
            cls._sessions[session_id]["state"] = state.value
            cls._sessions[session_id].update(kwargs)
    
    @classmethod
    def add_message(cls, session_id: str, direction: str, content: str):
        """Add message to session history."""
        if session_id in cls._sessions:
            cls._sessions[session_id]["messages"].append({
                "direction": direction,  # "outgoing" or "incoming"
                "content": content,
                "timestamp": datetime.now().isoformat()
            })


# ============================================================================
# Message Templates
# ============================================================================

def get_booking_request_message(
    patient_name: str,
    preferred_time: str,
    reason: str = "General checkup"
) -> str:
    """Generate initial booking request message."""
    return f"""Hello! 👋

I'm reaching out on behalf of *{patient_name}* through the AEGIS Health System.

They would like to book an appointment:
📅 *Preferred Time:* {preferred_time}
📋 *Reason:* {reason}

Is this time slot available? Please reply with:
- *YES* if available
- *NO* with alternative times if not available

Thank you! 🏥"""


def get_confirmation_message(patient_name: str, confirmed_time: str) -> str:
    """Generate confirmation message."""
    return f"""Perfect! ✅

The appointment for *{patient_name}* has been confirmed for:
📅 *{confirmed_time}*

They will receive a reminder before the appointment.

Thank you for using AEGIS Health System! 🙏"""


def get_alternative_request_message(patient_name: str) -> str:
    """Ask for alternative times."""
    return f"""Thank you for your response.

Could you please provide 2-3 alternative time slots that work for *{patient_name}*?

Format: Day, Time (e.g., "Monday 2pm, Tuesday 10am")"""


# ============================================================================
# Core WhatsApp Functions
# ============================================================================

def send_whatsapp_message(
    to_phone: str,
    message: str,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a WhatsApp message via Twilio.
    
    Args:
        to_phone: Recipient phone number (will be formatted for WhatsApp)
        message: Message content
        session_id: Optional session ID for tracking
        
    Returns:
        Dict with status and message SID
    """
    if not is_whatsapp_configured():
        return {
            "success": False,
            "error": "WhatsApp not configured. Set TWILIO_WHATSAPP_NUMBER."
        }
    
    client = get_twilio_client()
    
    # Format phone for WhatsApp
    to_whatsapp = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
    from_whatsapp = TWILIO_WHATSAPP_NUMBER if TWILIO_WHATSAPP_NUMBER.startswith("whatsapp:") else f"whatsapp:{TWILIO_WHATSAPP_NUMBER}"
    
    try:
        msg = client.messages.create(
            body=message,
            from_=from_whatsapp,
            to=to_whatsapp,
            status_callback=f"{AEGIS_BASE_URL}/whatsapp/status" if AEGIS_BASE_URL else None
        )
        
        # Track in session if provided
        if session_id:
            WhatsAppBookingSession.add_message(session_id, "outgoing", message)
        
        print(f"[WHATSAPP] Sent to {to_phone}: {message[:50]}...")
        
        return {
            "success": True,
            "message_sid": msg.sid,
            "status": msg.status
        }
        
    except Exception as e:
        print(f"[WHATSAPP ERROR] {e}")
        return {
            "success": False,
            "error": str(e)
        }


def initiate_booking_conversation(
    user_id: int,
    physician_name: str,
    physician_phone: str,
    patient_name: str,
    preferred_time: str,
    reason: str = "General checkup"
) -> Dict[str, Any]:
    """
    Initiate a WhatsApp booking conversation with a physician's office.
    
    Args:
        user_id: AEGIS user ID
        physician_name: Name of the physician
        physician_phone: Physician's WhatsApp number
        patient_name: Patient's name for the booking
        preferred_time: Preferred appointment time
        reason: Reason for visit
        
    Returns:
        Dict with session info and status
    """
    # Create booking session
    session_id = WhatsAppBookingSession.create(
        user_id=user_id,
        physician_phone=physician_phone,
        physician_name=physician_name,
        patient_name=patient_name,
        preferred_time=preferred_time,
        reason=reason
    )
    
    # Generate and send booking request
    message = get_booking_request_message(patient_name, preferred_time, reason)
    result = send_whatsapp_message(physician_phone, message, session_id)
    
    if result["success"]:
        # Log to database
        session = SessionLocal()
        try:
            log = models.HealthEvent(
                user_id=user_id,
                event_type="whatsapp_booking_initiated",
                data={
                    "session_id": session_id,
                    "physician": physician_name,
                    "phone": physician_phone,
                    "preferred_time": preferred_time,
                    "message_sid": result.get("message_sid")
                },
                timestamp=datetime.now()
            )
            session.add(log)
            session.commit()
        finally:
            session.close()
        
        return {
            "success": True,
            "session_id": session_id,
            "message": f"Booking request sent to {physician_name} via WhatsApp",
            "status": "awaiting_response"
        }
    
    return result


def process_incoming_message(
    from_phone: str,
    message_body: str
) -> Dict[str, Any]:
    """
    Process incoming WhatsApp message from physician's office.
    
    Args:
        from_phone: Sender's phone number
        message_body: Message content
        
    Returns:
        Dict with response action and message
    """
    # Find active session for this phone
    session = WhatsAppBookingSession.get_by_phone(from_phone)
    
    if not session:
        return {
            "action": "no_session",
            "response": "Thank you for your message. No active booking request found."
        }
    
    session_id = session["session_id"]
    message_lower = message_body.lower().strip()
    
    # Track incoming message
    WhatsAppBookingSession.add_message(session_id, "incoming", message_body)
    
    # Parse response based on current state
    if session["state"] == BookingState.INITIATED.value:
        # Check for confirmation
        if any(word in message_lower for word in ["yes", "available", "confirmed", "ok", "sure", "can"]):
            # Appointment confirmed!
            WhatsAppBookingSession.update_state(
                session_id, 
                BookingState.CONFIRMED,
                confirmed_time=session["preferred_time"]
            )
            
            # Send confirmation
            confirm_msg = get_confirmation_message(
                session["patient_name"],
                session["preferred_time"]
            )
            send_whatsapp_message(from_phone, confirm_msg, session_id)
            
            # Create appointment in database
            _create_appointment_record(session)
            
            return {
                "action": "confirmed",
                "session_id": session_id,
                "confirmed_time": session["preferred_time"],
                "response": confirm_msg
            }
        
        elif any(word in message_lower for word in ["no", "unavailable", "busy", "full", "cannot"]):
            # Not available, ask for alternatives
            WhatsAppBookingSession.update_state(session_id, BookingState.AWAITING_TIME_OPTIONS)
            
            alt_msg = get_alternative_request_message(session["patient_name"])
            send_whatsapp_message(from_phone, alt_msg, session_id)
            
            return {
                "action": "requesting_alternatives",
                "session_id": session_id,
                "response": alt_msg
            }
    
    elif session["state"] == BookingState.AWAITING_TIME_OPTIONS.value:
        # They're providing alternative times
        # Extract times and notify user (simplified - could use LLM for parsing)
        WhatsAppBookingSession.update_state(
            session_id,
            BookingState.TIME_PROPOSED,
            proposed_times=message_body
        )
        
        # Notify user about alternatives
        _notify_user_alternatives(session, message_body)
        
        return {
            "action": "alternatives_received",
            "session_id": session_id,
            "alternatives": message_body,
            "response": "Thank you! We'll confirm with the patient and get back to you."
        }
    
    # Default response
    return {
        "action": "message_logged",
        "session_id": session_id,
        "response": "Message received. Thank you!"
    }


def _create_appointment_record(session: Dict):
    """Create appointment record in database."""
    db = SessionLocal()
    try:
        # Create appointment
        appointment = models.HealthEvent(
            user_id=session["user_id"],
            event_type="appointment_booked",
            data={
                "physician": session["physician_name"],
                "phone": session["physician_phone"],
                "time": session["confirmed_time"],
                "reason": session["reason"],
                "booked_via": "whatsapp",
                "session_id": session["session_id"]
            },
            timestamp=datetime.now()
        )
        db.add(appointment)
        db.commit()
        print(f"[WHATSAPP] Appointment created for user {session['user_id']}")
    except Exception as e:
        print(f"[WHATSAPP ERROR] Failed to create appointment: {e}")
        db.rollback()
    finally:
        db.close()


def _notify_user_alternatives(session: Dict, alternatives: str):
    """Notify user about alternative time slots (placeholder - implement push notification)."""
    print(f"[WHATSAPP] User {session['user_id']} should be notified of alternatives: {alternatives}")
    # TODO: Implement push notification or in-app notification


# ============================================================================
# Webhook Response Generators
# ============================================================================

def generate_webhook_response(incoming_response: Dict) -> str:
    """Generate TwiML response for webhook."""
    response = MessagingResponse()
    
    if incoming_response.get("response"):
        response.message(incoming_response["response"])
    
    return str(response)


# ============================================================================
# Tool Function for Agent
# ============================================================================

def book_via_whatsapp(
    user_id: int,
    physician_name: str,
    physician_phone: str,
    preferred_time: str,
    reason: str = "General checkup"
) -> str:
    """
    Tool function for the agent to book appointments via WhatsApp.
    
    Returns a status message for the agent to relay to the user.
    """
    # Get patient name from database
    session = SessionLocal()
    try:
        user = session.query(models.User).filter(models.User.id == user_id).first()
        patient_name = user.email.split("@")[0] if user else f"Patient {user_id}"
    finally:
        session.close()
    
    result = initiate_booking_conversation(
        user_id=user_id,
        physician_name=physician_name,
        physician_phone=physician_phone,
        patient_name=patient_name,
        preferred_time=preferred_time,
        reason=reason
    )
    
    if result["success"]:
        return f"""✅ WhatsApp booking request sent!

📱 **Sent to:** {physician_name} ({physician_phone})
📅 **Requested time:** {preferred_time}
📋 **Reason:** {reason}

I'll notify you when they respond. The office typically replies within a few hours during business hours."""
    else:
        return f"""❌ Could not send WhatsApp booking request.

**Error:** {result.get('error', 'Unknown error')}

Would you like me to try calling the office instead?"""


def get_booking_status(session_id: str) -> str:
    """Get status of a WhatsApp booking session."""
    session = WhatsAppBookingSession.get(session_id)
    
    if not session:
        return "Booking session not found."
    
    state = session["state"]
    
    if state == BookingState.CONFIRMED.value:
        return f"✅ Appointment CONFIRMED for {session['confirmed_time']} with {session['physician_name']}"
    elif state == BookingState.INITIATED.value:
        return f"⏳ Waiting for response from {session['physician_name']}..."
    elif state == BookingState.AWAITING_TIME_OPTIONS.value:
        return f"📅 The requested time wasn't available. Waiting for alternative times..."
    elif state == BookingState.TIME_PROPOSED.value:
        return f"📋 Alternative times received: {session.get('proposed_times', 'Check messages')}"
    elif state == BookingState.REJECTED.value:
        return f"❌ Booking was not successful with {session['physician_name']}"
    else:
        return f"Status: {state}"
