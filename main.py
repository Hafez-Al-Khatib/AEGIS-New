from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware  # <-- Added for frontend communication
from sqlalchemy.orm import Session
import models, schemas, database, influx_ingester
from agents.sentinel import sentinel
from agents.ingestor import extract_medical_text
from agents.hospital_service import hospital_manager, EmergencySeverity
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import os
import shutil

# Config
models.Base.metadata.create_all(bind=database.engine)
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user

app = FastAPI(title="Aegis API", description="Backend for Health Monitoring System", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already exists")
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password, operating_mode=models.OperatingMode.PASSIVE)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@app.put("/users/me/mode", response_model=schemas.User)
def set_user_mode(mode_update: schemas.OperatingModeSchema, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    current_user.operating_mode = mode_update.mode
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

@app.post("/health_events/me", response_model=schemas.HealthEvent)
def create_health_event_for_me(health_event: schemas.HealthEventCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_health_event = models.HealthEvent(**health_event.model_dump(), user_id=current_user.id)
    db.add(db_health_event)
    db.commit()
    db.refresh(db_health_event)
    return db_health_event

@app.get("/health_events/me", response_model=List[schemas.HealthEvent])
def read_health_events_for_me(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    health_events = db.query(models.HealthEvent).filter(models.HealthEvent.user_id == current_user.id).offset(skip).limit(limit).all()
    return health_events

@app.post("/vitals/me/")
def log_vitals(
    vitals: schemas.VitalsLog, 
    current_user: models.User = Depends(get_current_user)
):
    """
    Receives a new vitals reading (from hardware like ESP-32)
    and logs it to InfluxDB for the current user.
    Includes: heart_rate (bpm), spo2 (%), temperature (°C - optional)
    """
    if not influx_ingester.write_api:
         raise HTTPException(status_code=500, detail="InfluxDB client not initialized.")
    try:
        influx_ingester.write_vitals(
            user_id=current_user.id,
            heart_rate=vitals.heart_rate,
            spo2=vitals.spo2,
            temperature=vitals.temperature
        )
        return {"status": "success", "message": "Vitals logged successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing to InfluxDB: {e}")


@app.get("/vitals/me", response_model=List[Dict[str, Any]])
def read_vitals(range: str = "-1h", current_user: models.User = Depends(get_current_user)):
    """
    Reads the time-series vital signs data for the current user from the last hour or specified range.
    """
    try:
        results = influx_ingester.query_vitals(
            user_id=current_user.id,
            time_range=range
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/emergency/set-location")
def set_emergency_location(
    location: schemas.UserLocation,
    current_user: models.User = Depends(get_current_user)
):
    """
    Set user's location for emergency services.
    This location is used to find the nearest hospital.
    """
    try:
        hospital_manager.set_user_location(location.latitude, location.longitude)
        return {
            "status": "success",
            "message": "Location set for emergency services",
            "location": {"latitude": location.latitude, "longitude": location.longitude}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/emergency/nearest-hospital")
def get_nearest_hospital(
    current_user: models.User = Depends(get_current_user),
    radius_km: int = 10
):
    """
    Get the nearest hospital to the user's current location.
    """
    try:
        hospital_manager.find_nearby_hospitals(radius_km=radius_km)
        nearest = hospital_manager.get_nearest_hospital()
        
        if not nearest:
            raise HTTPException(status_code=404, detail="No hospitals found in the specified radius")
        
        return nearest
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/emergency/nearby-hospitals")
def get_nearby_hospitals(
    current_user: models.User = Depends(get_current_user),
    radius_km: int = 10,
    limit: int = 5
):
    """
    Get list of nearby hospitals within the specified radius.
    """
    try:
        hospitals = hospital_manager.find_nearby_hospitals(radius_km=radius_km)
        return {
            "user_id": current_user.id,
            "hospitals": hospitals[:limit],
            "total_found": len(hospitals),
            "radius_km": radius_km
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/emergency/contact")
def initiate_emergency_contact(
    emergency_request: schemas.EmergencyContactRequest,
    current_user: models.User = Depends(get_current_user)
):
    """
    Manually initiate emergency hospital contact.
    Calls nearest hospital and logs emergency event.
    """
    try:
        emergency_log = hospital_manager.call_emergency_services(
            user_id=current_user.id,
            user_email=current_user.email,
            severity=emergency_request.severity,
            medical_summary=emergency_request.medical_summary,
            latitude=emergency_request.latitude,
            longitude=emergency_request.longitude
        )
        
        # Log emergency event in database
        db_health_event = models.HealthEvent(
            user_id=current_user.id,
            event_type="emergency_contact",
            data=emergency_log
        )
        db = database.SessionLocal()
        db.add(db_health_event)
        db.commit()
        db.close()
        
        return emergency_log
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/emergency/contact-card")
def get_emergency_contact_card(
    current_user: models.User = Depends(get_current_user)
):
    """
    Get emergency contact information card for the user.
    """
    try:
        contact_card = hospital_manager.create_emergency_contact_card(
            user_id=current_user.id,
            user_email=current_user.email
        )
        return contact_card
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/analyze/document", tags=["Agents"])
async def analyze_document(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    latitude: Optional[float] = None,
    longitude: Optional[float] = None
):
    """
    Multi-Agent Workflow:
    1. Ingestor (Vision) -> JSON + Store in Memory
    2. Sentinel (Reasoning) -> Advice + Emergency Detection
    
    If emergency is detected, automatically contacts nearest hospital.
    Optional: Pass latitude and longitude for emergency location services.
    """
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # Agent 1: Vision - Extract medical data and store in memory
        ingest_result = extract_medical_text(
            file_path=temp_path,
            patient_id=str(current_user.id)
        )
        
        if "error" in ingest_result:
            raise HTTPException(status_code=400, detail=ingest_result["error"])
        
        extracted_data = ingest_result.get("content", "")
        
        # Prepare user location if provided
        user_location = None
        if latitude and longitude:
            user_location = {"latitude": latitude, "longitude": longitude}
        
        # Agent 2: Reasoning - Analyze with emergency detection
        analysis = sentinel.analyze_health_record(
            extracted_data=extracted_data,
            user_context=f"User: {current_user.email}",
            user_id=current_user.id,
            user_email=current_user.email,
            user_location=user_location
        )
        
        return {
            "status": "success",
            "document_id": ingest_result.get("document_id"),
            "vision_output": extracted_data,
            "summary": ingest_result.get("summary"),
            "reasoning_output": analysis,
            "emergency_detected": analysis.get("is_emergency", False),
            "severity_level": analysis.get("severity_level"),
            "emergency_contact_initiated": "emergency_contact" in analysis
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/documents/ingest", tags=["Documents"])
async def ingest_document(
    file: UploadFile = File(...),
    doc_type: str = "medical_report",
    current_user: models.User = Depends(get_current_user)
):
    """
    Ingest a document (PDF, image, or DICOM) into memory
    
    Supported formats:
    - PDF (.pdf) - Full document extraction
    - Images (.jpg, .jpeg, .png, .gif, .bmp) - OCR with vision AI
    - DICOM (.dcm, .dicom) - Medical imaging with metadata extraction
    
    Document types: medical_report, lab_result, prescription, imaging, dicom_scan, etc.
    """
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        result = extract_medical_text(
            file_path=temp_path,
            patient_id=str(current_user.id)
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return {
            "status": "success",
            "document_id": result.get("document_id"),
            "summary": result.get("summary"),
            "content_length": len(result.get("content", "")),
            "file_type": result.get("file_type")
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/documents/memory/info", tags=["Documents"])
def get_memory_info(current_user: models.User = Depends(get_current_user)):
    """
    Get statistics about stored documents in memory
    """
    from agents.ingestor import get_memory_info
    return get_memory_info()


@app.get("/documents/search", tags=["Documents"])
def search_documents(
    query: str,
    search_type: str = "keyword",
    current_user: models.User = Depends(get_current_user)
):
    """
    Search stored documents in memory
    
    search_type options:
    - "keyword": Search by keyword in summaries
    - "type": Search by document type (medical_report, lab_result, etc.)
    - "patient": Search by patient ID
    """
    from agents.ingestor import vision_agent
    
    try:
        results = vision_agent.search_memory(query, search_type=search_type)
        return {
            "query": query,
            "search_type": search_type,
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/documents/patient/{patient_id}", tags=["Documents"])
def get_patient_documents(
    patient_id: str,
    current_user: models.User = Depends(get_current_user)
):
    """
    Get all documents for a specific patient
    """
    from agents.ingestor import search_patient_documents
    
    documents = search_patient_documents(patient_id)
    return {
        "patient_id": patient_id,
        "document_count": len(documents),
        "documents": documents
    }


@app.delete("/documents/memory", tags=["Documents"])
def clear_document_memory(current_user: models.User = Depends(get_current_user)):
    """
    Clear all documents from memory (Admin function)
    """
    from agents.ingestor import vision_agent
    
    vision_agent.clear_memory()
    return {"status": "success", "message": "Memory cleared"}

