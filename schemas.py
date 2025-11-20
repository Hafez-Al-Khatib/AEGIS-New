from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict, Any
from models import OperatingMode

class OperatingModeSchema(BaseModel):
    mode: OperatingMode

    class Config:
        use_enum_values = True

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    operating_mode: OperatingMode
    created_at: datetime

    class Config:
        from_attributes = True
        use_enum_values = True

class HealthEventBase(BaseModel):
    event_type: str
    data: Dict[str, Any]

class HealthEventCreate(HealthEventBase):
    pass

class HealthEvent(HealthEventBase):
    id: int
    user_id: int
    timestamp: datetime

    class Config:
        from_attributes = True

class Vitals(BaseModel):
    heart_rate: float
    spo2: float
    temperature: Optional[float] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class SentinelQuery(BaseModel):
    medication_name: str

class VitalsLog(BaseModel):
    heart_rate: float
    spo2: float
    temperature: Optional[float] = None


# Emergency & Hospital Service Schemas

class UserLocation(BaseModel):
    """User location for emergency services"""
    latitude: float
    longitude: float


class EmergencyContactRequest(BaseModel):
    """Request to initiate emergency contact"""
    severity: str  # "critical", "high", "moderate", "low"
    medical_summary: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class HospitalInfo(BaseModel):
    """Information about a hospital"""
    name: str
    latitude: float
    longitude: float
    distance_km: float
    address: str = "N/A"
    phone: str = "N/A"
    emergency: str = "unknown"


class EmergencyContactCard(BaseModel):
    """Emergency contact information card"""
    user_id: int
    user_email: str
    emergency_number: str
    nearest_hospital: Optional[HospitalInfo] = None
    all_nearby_hospitals: Optional[list] = None
    user_location: Optional[Dict[str, float]] = None
    created_at: datetime