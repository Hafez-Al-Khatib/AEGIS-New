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