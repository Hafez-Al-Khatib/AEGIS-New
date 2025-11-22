from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
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
from alert_engine import evaluate_sentinel_output
from observability import log_agent_event

# After Sentinel analysis
alert_needed, reason = evaluate_sentinel_output(analysis)

if alert_needed:
    log_agent_event(
        agent_name="Sentinel",
        user_id=current_user.id,
        event="ALERT_TRIGGERED",
        extra={"reason": reason}
    )

    db_alert = models.Alert(
        user_id=current_user.id,
        message=reason,
        severity="HIGH"
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)

    return {
        "status": "ALERT",
        "message": reason,
        "vision_output": extracted_data,
        "reasoning_output": analysis
    }

return {
    "status": "success",
    "vision_output": extracted_data,
    "reasoning_output": analysis
}
