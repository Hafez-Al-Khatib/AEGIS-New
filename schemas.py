from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict, Any, List
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

class WatchVitalsSync(BaseModel):
    """
    Samsung Galaxy Watch 4 vitals sync schema.
    Supports all metrics available from the watch.
    """
    # Core vitals
    heart_rate: Optional[float] = None
    spo2: Optional[float] = None
    
    # Blood pressure (requires calibration)
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    
    # ECG data
    ecg_classification: Optional[str] = None  # "Sinus Rhythm", "AFib", "Inconclusive"
    ecg_heart_rate: Optional[int] = None
    
    # Body composition (BIA sensor)
    body_fat_percent: Optional[float] = None
    skeletal_muscle_mass: Optional[float] = None
    body_water_percent: Optional[float] = None
    bmr: Optional[int] = None  # Basal metabolic rate
    
    # Stress & Sleep
    stress_level: Optional[int] = None  # 0-100
    sleep_score: Optional[int] = None
    sleep_duration_minutes: Optional[int] = None
    deep_sleep_minutes: Optional[int] = None
    rem_sleep_minutes: Optional[int] = None
    
    # Activity
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict, Any, List
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

class WatchVitalsSync(BaseModel):
    """
    Samsung Galaxy Watch 4 vitals sync schema.
    Supports all metrics available from the watch.
    """
    # Core vitals
    heart_rate: Optional[float] = None
    spo2: Optional[float] = None
    
    # Blood pressure (requires calibration)
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    
    # ECG data
    ecg_classification: Optional[str] = None  # "Sinus Rhythm", "AFib", "Inconclusive"
    ecg_heart_rate: Optional[int] = None
    
    # Body composition (BIA sensor)
    body_fat_percent: Optional[float] = None
    skeletal_muscle_mass: Optional[float] = None
    body_water_percent: Optional[float] = None
    bmr: Optional[int] = None  # Basal metabolic rate
    
    # Stress & Sleep
    stress_level: Optional[int] = None  # 0-100
    sleep_score: Optional[int] = None
    sleep_duration_minutes: Optional[int] = None
    deep_sleep_minutes: Optional[int] = None
    rem_sleep_minutes: Optional[int] = None
    
    # Activity
    steps: Optional[int] = None
    calories_burned: Optional[int] = None
    active_minutes: Optional[int] = None
    floors_climbed: Optional[int] = None
    
    # Temperature (during sleep)
    skin_temperature: Optional[float] = None
    
    # Metadata
    timestamp: Optional[datetime] = None
    source: str = "galaxy_watch_4"  # Identify data source

class WatchVitalsBatch(BaseModel):
    """Batch sync of multiple readings from watch."""
    readings: List[WatchVitalsSync]

class Alert(BaseModel):
    id: int
    user_id: int
    message: str
    severity: str
    timestamp: datetime

    class Config:
        from_attributes = True

class UserLocation(BaseModel):
    lat: float
    lon: float

class ChatRequest(BaseModel):
    message: str
    query: Optional[str] = None
    history: Optional[List] = []
    session_id: Optional[int] = None
    user_location: Optional[UserLocation] = None
    voice_enabled: Optional[bool] = False

class ChatResponse(BaseModel):
    response: str

class ChatMessageBase(BaseModel):
    role: str
    content: str

class ChatMessage(ChatMessageBase):
    id: int
    session_id: int
    timestamp: datetime

    class Config:
        from_attributes = True

class ChatSessionBase(BaseModel):
    title: str

class ChatSessionCreate(ChatSessionBase):
    pass

class ChatSession(ChatSessionBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ============== ADVANCED AGENTS SCHEMAS ==============

class HealthGoalBase(BaseModel):
    description: str

class HealthGoalCreate(HealthGoalBase):
    pass

class HealthGoal(HealthGoalBase):
    id: int
    user_id: int
    status: str
    progress: int = 0
    category: Optional[str] = None  # diet, exercise, medication, monitoring, lifestyle
    priority: Optional[str] = "medium"  # high, medium, low
    rationale: Optional[str] = None  # Clinical reason for goal
    condition_link: Optional[str] = None  # Which condition this addresses
    deadline: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DailySummary(BaseModel):
    id: int
    user_id: int
    date: datetime
    summary: str
    mood: Optional[str] = None

    class Config:
        from_attributes = True