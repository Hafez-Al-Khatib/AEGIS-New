from sqlalchemy import Column, Integer, String, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime
from database import Base

class OperatingMode(str, enum.Enum):
    # Add a default value for operating_mode
    # This will be used in the User model
    DEFAULT = "passive"
    PASSIVE = "passive"
    ADVISORY = "advisory"
    GUARDIAN = "guardian"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    phone_number = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    operating_mode = Column(Enum(OperatingMode), default=OperatingMode.PASSIVE, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    health_events = relationship("HealthEvent", back_populates="owner")

class HealthEvent(Base):
    __tablename__ = "health_events"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_type = Column(String, nullable=False)
    data = Column(JSON)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="health_events")

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(String)
    severity = Column(String)  # LOW, MEDIUM, HIGH
    timestamp = Column(DateTime, default=datetime.utcnow)

class Physician(Base):
    __tablename__ = "physicians"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)
    specialty = Column(String)
    clinic = Column(String)
    phone = Column(String)
    image_url = Column(String)
    
    # Relationship to user (optional, if we want to make it a personal address book)
    # For now, let's assume it's a global directory or personal. User_id implies personal.

class Medication(Base):
    __tablename__ = "medications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)
    dosage = Column(String)
    frequency = Column(String)
    start_date = Column(String) # ISO format or simple string
    end_date = Column(String)
    status = Column(String) # Active, Discontinued

class Condition(Base):
    __tablename__ = "conditions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)
    diagnosis_date = Column(String)
    status = Column(String) # Active, Resolved, Chronic

class Allergy(Base):
    __tablename__ = "allergies"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    allergen = Column(String, index=True)
    reaction = Column(String)
    severity = Column(String) # Mild, Moderate, Severe

class LabResult(Base):
    __tablename__ = "lab_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    test_name = Column(String, index=True)
    value = Column(String)
    unit = Column(String)
    reference_range = Column(String)
    date = Column(String)

class MedicalNote(Base):
    __tablename__ = "medical_notes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(String)
    provider = Column(String)
    note_text = Column(String)
    summary = Column(String)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"))
    role = Column(String) # user, assistant
    content = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("ChatSession", back_populates="messages")

class DailySummary(Base):
    __tablename__ = "daily_summaries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(String, index=True) # YYYY-MM-DD
    summary = Column(String)
    mood = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class HealthGoal(Base):
    __tablename__ = "health_goals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    description = Column(String)
    category = Column(String, nullable=True)  # diet, exercise, medication, monitoring, lifestyle
    priority = Column(String, default="medium")  # high, medium, low
    rationale = Column(String, nullable=True)  # Why this goal was recommended (clinical basis)
    condition_link = Column(String, nullable=True)  # Which condition this goal addresses
    progress = Column(Integer, default=0)  # 0-100 percentage
    status = Column(String, default="active")  # active, completed, abandoned
    deadline = Column(String, nullable=True)
    habitica_task_id = Column(String, nullable=True)  # Sync with Habitica
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class EmergencyContact(Base):
    """Emergency contacts for critical health alerts and emergency calls."""
    __tablename__ = "emergency_contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    relationship = Column(String)  # spouse, parent, child, sibling, friend, physician
    phone_number = Column(String, nullable=False)  # E.164 format: +1234567890
    email = Column(String, nullable=True)
    priority = Column(Integer, default=1)  # 1 = first to call, 2 = second, etc.
    is_active = Column(String, default="true")
    notify_on_critical = Column(String, default="true")  # Auto-notify on critical vitals
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmergencyCallLog(Base):
    """Log of all emergency calls made by the system."""
    __tablename__ = "emergency_call_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    contact_id = Column(Integer, ForeignKey("emergency_contacts.id"), nullable=True)
    trigger_type = Column(String)  # "vital_alert", "user_request", "agent_detected"
    trigger_details = Column(JSON)  # What triggered the call
    call_sid = Column(String)  # Twilio call SID
    status = Column(String)  # initiated, ringing, answered, completed, failed, no-answer
    duration_seconds = Column(Integer, nullable=True)
    recording_url = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

