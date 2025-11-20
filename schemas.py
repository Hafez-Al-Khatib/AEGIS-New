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