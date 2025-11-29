from fastapi import FastAPI, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import time
import shutil

import models, schemas, database, influx_ingester
from agents import ingestor, sentinel
from observability import log_api_call, log_agent_event
from alert_engine import evaluate_vitals, evaluate_sentinel_output
from prometheus_fastapi_instrumentator import Instrumentator
from metrics import AGENT_CALLS, AGENT_LATENCY
import edge_tts
import uuid
import aiofiles
from fastapi.staticfiles import StaticFiles

# ================== CONFIG ==================
models.Base.metadata.create_all(bind=database.engine)
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2scheme = OAuth2PasswordBearer(tokenUrl="token")

# ================== APP ======================
app = FastAPI(title="Aegis API",
              description="Backend for Health Monitoring System",
              version="1.0.0")

# ================== MIDDLEWARE ==============
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

Instrumentator().instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False
)

# ================== STATIC FILES ============
AUDIO_DIR = "audio_cache"
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")

# ================== AUDIO HELPER ============
async def generate_audio(text: str) -> str:
    """Generates TTS audio using Edge TTS and returns the filename."""
    try:
        filename = f"{uuid.uuid4()}.mp3"
        filepath = os.path.join(AUDIO_DIR, filename)
        communicate = edge_tts.Communicate(text, "en-US-AriaNeural") # Natural female voice
        await communicate.save(filepath)
        return filename
    except Exception as e:
        print(f"Error generating audio: {e}")
        return None

# ================== HEALTH CONNECT ===========
try:
    from integrations.health_connect import router as health_connect_router
    app.include_router(health_connect_router)
    print("✅ Health Connect integration loaded")
except ImportError as e:
    print(f"⚠️ Health Connect integration not loaded: {e}")

# ================== UTILS ====================
def verify_password(plain_password, hashed_password):
    # Convert to bytes and truncate to 72 bytes for bcrypt
    password_bytes = plain_password.encode('utf-8')[:72]
    return pwd_context.verify(password_bytes, hashed_password)

def get_password_hash(password: str):
    # Convert to bytes and truncate to 72 bytes for bcrypt
    password_bytes = password.encode('utf-8')[:72]
    return pwd_context.hash(password_bytes)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request,
                     token: str = Depends(oauth2scheme),
                     db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    request.state.user_id = user.id
    return user

# ================= AUTH ======================
@app.post("/token", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):

    user = db.query(models.User)\
        .filter(models.User.email == form.username).first()

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect credentials")

    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {"access_token": access_token, "token_type": "bearer"}

# ================= USERS =====================
@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User)\
        .filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email exists")

    db_user = models.User(
        email=user.email,
        phone_number=user.phone_number,
        hashed_password=get_password_hash(user.password),
        operating_mode=models.OperatingMode.PASSIVE
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user

@app.get("/users/me", response_model=schemas.User)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user

@app.put("/users/me/mode", response_model=schemas.User)
def set_user_mode(mode_update: schemas.OperatingModeSchema, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    current_user.operating_mode = mode_update.mode
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

# ================= HEALTH EVENTS =================
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

# ============== VITALS + ALERTS =============
@app.post("/vitals/me")
def log_vitals(vitals: schemas.VitalsLog,
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):

    vitals_data = {
        "heart_rate": vitals.heart_rate,
        "spo2": vitals.spo2,
        "source": "manual"
    }
    
    # Store in SQLite (primary storage - no InfluxDB required)
    event = models.HealthEvent(
        user_id=current_user.id,
        event_type="vitals",
        data=vitals_data,
        timestamp=datetime.utcnow()
    )
    db.add(event)
    db.commit()

    # Optional: Also write to InfluxDB if available
    try:
        influx_ingester.write_vitals(
            user_id=current_user.id,
            heart_rate=vitals.heart_rate,
            spo2=vitals.spo2
        )
    except Exception:
        pass  # InfluxDB is optional

    alert, message = evaluate_vitals(
        vitals.heart_rate,
        vitals.spo2
    )

    response = {"status": "success"}
    
    if alert:
        db_alert = models.Alert(
            user_id=current_user.id,
            message=message,
            severity="HIGH"
        )
        db.add(db_alert)
        db.commit()

        log_agent_event("Sentinel", current_user.id,
                        "ALERT_FROM_VITALS", 0,
                        {"message": message})

        response = {"status": "ALERT", "message": message}
    
    # Check for sustained critical vitals and auto-trigger emergency call
    try:
        from integrations.twilio_emergency import auto_trigger_emergency_if_critical
        emergency_result = auto_trigger_emergency_if_critical(current_user.id, vitals_data)
        if emergency_result:
            response["emergency_call"] = emergency_result
            response["status"] = "EMERGENCY"
    except Exception as e:
        print(f"[EMERGENCY CHECK ERROR] {e}")

    return response

@app.get("/vitals/me", response_model=List[Dict[str, Any]])
def read_vitals(range: str = "-1h", current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Reads the time-series vital signs data for the current user from HealthEvents table.
    """
    # Query directly from HealthEvents table (CSV-ingested data)
    try:
        events = db.query(models.HealthEvent).filter(
            models.HealthEvent.user_id == current_user.id,
            models.HealthEvent.event_type == "vitals"
        ).order_by(models.HealthEvent.timestamp.desc()).limit(100).all()
        
        print(f"[VITALS] Found {len(events)} vitals for user {current_user.id}")
        
        # Transform to expected format
        results = []
        for e in events:
            if e.data:
                results.append({
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "heart_rate": e.data.get("heart_rate"),
                    "spo2": e.data.get("spo2"),
                    "temperature": e.data.get("temperature"),
                    "systolic_bp": e.data.get("systolic_bp"),
                    "diastolic_bp": e.data.get("diastolic_bp"),
                    "respiratory_rate": e.data.get("respiratory_rate")
                })
        
        # Debug: show first record
        if results:
            print(f"[VITALS] Sample: {results[0]}")
        
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/alerts/me", response_model=List[schemas.Alert])
def get_alerts(db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):

    return db.query(models.Alert)\
             .filter(models.Alert.user_id==current_user.id)\
             .order_by(models.Alert.timestamp.desc()).all()


# ============== SAMSUNG GALAXY WATCH SYNC ============
@app.post("/vitals/watch/sync", tags=["Vitals"])
def sync_watch_vitals(
    vitals: schemas.WatchVitalsSync,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Sync a single reading from Samsung Galaxy Watch 4.
    Accepts all available metrics from the watch.
    """
    # Build data payload from non-None values
    data = {k: v for k, v in vitals.model_dump().items() 
            if v is not None and k not in ['timestamp', 'source']}
    data['source'] = vitals.source
    
    # Create health event
    event = models.HealthEvent(
        user_id=current_user.id,
        event_type="vitals",
        data=data,
        timestamp=vitals.timestamp or datetime.utcnow()
    )
    db.add(event)
    db.commit()
    
    print(f"[WATCH SYNC] Saved vitals from {vitals.source}: HR={vitals.heart_rate}, SpO2={vitals.spo2}")
    
    # Check for alerts on critical vitals
    alerts = []
    if vitals.heart_rate:
        if vitals.heart_rate < 40 or vitals.heart_rate > 150:
            alerts.append(f"Heart rate {vitals.heart_rate} bpm is outside normal range")
    if vitals.spo2 and vitals.spo2 < 90:
        alerts.append(f"SpO2 {vitals.spo2}% is critically low")
    if vitals.systolic_bp and (vitals.systolic_bp > 180 or vitals.systolic_bp < 80):
        alerts.append(f"Blood pressure {vitals.systolic_bp}/{vitals.diastolic_bp} is concerning")
    
    if alerts:
        for msg in alerts:
            db_alert = models.Alert(
                user_id=current_user.id,
                message=msg,
                severity="HIGH"
            )
            db.add(db_alert)
        db.commit()
        return {"status": "ALERT", "messages": alerts, "event_id": event.id}
    
    return {"status": "success", "event_id": event.id}

@app.post("/vitals/watch/batch", tags=["Vitals"])
def sync_watch_vitals_batch(
    batch: schemas.WatchVitalsBatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Batch sync multiple readings from Samsung Galaxy Watch 4.
    Use this for syncing historical data or multiple readings at once.
    """
    saved = 0
    for vitals in batch.readings:
        data = {k: v for k, v in vitals.model_dump().items() 
                if v is not None and k not in ['timestamp', 'source']}
        data['source'] = vitals.source
        
        event = models.HealthEvent(
            user_id=current_user.id,
            event_type="vitals",
            data=data,
            timestamp=vitals.timestamp or datetime.utcnow()
        )
        db.add(event)
        saved += 1
    
    db.commit()
    print(f"[WATCH SYNC] Batch saved {saved} readings from watch")
    
    return {"status": "success", "saved": saved}

@app.get("/vitals/watch/latest", tags=["Vitals"])
def get_latest_watch_vitals(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Get the latest vitals reading from Galaxy Watch.
    Returns comprehensive health metrics.
    """
    event = db.query(models.HealthEvent).filter(
        models.HealthEvent.user_id == current_user.id,
        models.HealthEvent.event_type == "vitals"
    ).order_by(models.HealthEvent.timestamp.desc()).first()
    
    if not event:
        return {"error": "No vitals data found"}
    
    return {
        "timestamp": event.timestamp.isoformat(),
        **event.data
    }


# ============== ANALYZE DOCUMENT ============
@app.post("/analyze/document", tags=["Agents"])
def analyze_document(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    temp = f"temp_{file.filename}"
    with open(temp, "wb") as f:
        f.write(file.file.read())

    try:
        AGENT_CALLS.labels("Ingestor").inc()
        t0 = time.perf_counter()
        data = ingestor.extract_medical_data(temp, user_id=current_user.id)
        AGENT_LATENCY.labels("Ingestor").observe(time.perf_counter() - t0)

        # Ingestor now saves to Knowledge Base automatically
        # Sentinel agent is reserved for real-time vitals monitoring and chat
        # Chat can access KB via read_medical_history tool
        
        if data.get("error"):
            raise HTTPException(status_code=500, detail=data["error"])
            
        # TRIGGER ETL: Extract structured data and save to DB
        try:
            markdown_text = data.get("markdown", "")
            if markdown_text:
                structured_data = sentinel.sentinel.extract_structured_data(markdown_text)
                
                # Save to DB
                if structured_data:
                    # Medications
                    for med in structured_data.get("medications", []):
                        db_med = models.Medication(
                            user_id=current_user.id,
                            name=med.get("name"),
                            dosage=med.get("dosage"),
                            frequency=med.get("frequency"),
                            status=med.get("status", "Active")
                        )
                        db.add(db_med)
                        
                    # Conditions
                    for cond in structured_data.get("conditions", []):
                        db_cond = models.Condition(
                            user_id=current_user.id,
                            name=cond.get("name"),
                            diagnosis_date=cond.get("diagnosis_date"),
                            status=cond.get("status", "Active")
                        )
                        db.add(db_cond)
                        
                    # Allergies
                    for alg in structured_data.get("allergies", []):
                        db_alg = models.Allergy(
                            user_id=current_user.id,
                            allergen=alg.get("allergen"),
                            reaction=alg.get("reaction"),
                            severity=alg.get("severity")
                        )
                        db.add(db_alg)
                        
                    # Lab Results
                    for lab in structured_data.get("lab_results", []):
                        db_lab = models.LabResult(
                            user_id=current_user.id,
                            test_name=lab.get("test_name"),
                            value=str(lab.get("value")), # Ensure string
                            unit=lab.get("unit"),
                            reference_range=lab.get("reference_range"),
                            date=lab.get("date")
                        )
                        db.add(db_lab)

                    # Medical Notes
                    for note in structured_data.get("medical_notes", []):
                        db_note = models.MedicalNote(
                            user_id=current_user.id,
                            date=note.get("date"),
                            provider=note.get("provider"),
                            note_text=note.get("note_text"),
                            summary=note.get("summary")
                        )
                        db.add(db_note)
                        
                    db.commit()
                    print(f"[ETL] Saved structured data for User {current_user.id}")
        except Exception as e:
            print(f"[ETL ERROR] Failed to save structured data: {e}")
        
        # Return the ingestor's markdown analysis
        return {
            "status": "success",
            "analysis": data.get("markdown", ""),
            "page_count": data.get("page_count", 1),
            "kb_path": data.get("kb_path"),
            "message": "Document analyzed, encrypted, and structured data extracted."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp):
            os.remove(temp)

@app.post("/analyze/vision", tags=["Agents"])
async def analyze_vision(
    file: UploadFile = File(...),
    prompt: str = Form("Analyze this medical image and identify any medications or conditions."),
    current_user: models.User = Depends(get_current_user)
):
    """
    Analyzes an uploaded medical image using Gemini Vision.
    """
    try:
        AGENT_CALLS.labels("Vision").inc()
        t0 = time.perf_counter()
        
        # Read file bytes
        image_data = await file.read()
        
        # Call Vision Engine
        from agents.llm_engine import analyze_medical_image
        analysis = analyze_medical_image(image_data, prompt)
        
        AGENT_LATENCY.labels("Vision").observe(time.perf_counter() - t0)
        
        return {
            "status": "success",
            "analysis": analysis,
            "filename": file.filename
        }
    except Exception as e:
        print(f"[VISION ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.responses import StreamingResponse
import json

@app.post("/chat", tags=["Agents"])
async def chat_with_sentinel(
    request: schemas.ChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        AGENT_CALLS.labels("Sentinel").inc()
        
        # Pass user context - extract values before session closes
        user_id = current_user.id
        user_email = current_user.email
        
        # Build user context with location if available
        user_context = f"User: {user_email}"
        if request.user_location:
            user_context += f"\nUser Location: ({request.user_location.lat}, {request.user_location.lon})"
        
        query_text = request.message if request.message else request.query
        
        # Save User Message if session_id provided
        if request.session_id:
            user_msg = models.ChatMessage(
                session_id=request.session_id,
                role="user",
                content=query_text
            )
            db.add(user_msg)
            db.commit()

        # Generator for streaming response
        async def response_generator():
            full_response = ""
            t0 = time.perf_counter()
            
            # Call Sentinel (Assuming sentinel.chat can yield chunks or we simulate it for now)
            # Since LangGraph stream is synchronous in some contexts, we might need to adjust.
            # For now, let's get the full response and simulate streaming to the frontend 
            # if the underlying agent doesn't support async streaming easily yet.
            # Ideally, we'd use sentinel.graph.stream()
            
            # TODO: Refactor Sentinel to support true async streaming. 
            # For this step, we will fetch the full response and stream it to the client
            # to enable the frontend "typing" effect immediately, while we work on true streaming.
            
            # Extract user location if provided
            user_loc = None
            if request.user_location:
                user_loc = {"lat": request.user_location.lat, "lon": request.user_location.lon}
            
            response_text = sentinel.sentinel.chat(
                query=query_text,
                history=request.history or [],
                user_context=user_context,
                user_id=user_id,
                user_location=user_loc
            )
            
            # Stream the response word by word (Simulation for UI effect)
            words = response_text.split(" ")
            for i, word in enumerate(words):
                chunk = word + " "
                full_response += chunk
                yield json.dumps({"token": chunk}) + "\n"
                # time.sleep(0.05) # Simulate network delay (optional, remove for prod)
            
            # Generate Audio if requested
            if request.voice_enabled:
                audio_filename = await generate_audio(full_response)
                if audio_filename:
                    audio_url = f"/audio/{audio_filename}"
                    yield json.dumps({"audio_url": audio_url}) + "\n"
                # time.sleep(0.05) # Simulate network delay (optional, remove for prod)
            
            AGENT_LATENCY.labels("Sentinel").observe(time.perf_counter() - t0)
            
            # Save Assistant Message if session_id provided
            if request.session_id:
                # We need a new DB session here because the generator runs after the request handler returns
                # But actually, we can't easily use the dependency db session in a background generator 
                # if it's closed. 
                # Better approach: Save AFTER streaming is done using a fresh session or 
                # just save it here if we are sure.
                
                # Re-opening session for the generator context
                with database.SessionLocal() as db_gen:
                    asst_msg = models.ChatMessage(
                        session_id=request.session_id,
                        role="assistant",
                        content=full_response
                    )
                    db_gen.add(asst_msg)
                    db_gen.commit()

        return StreamingResponse(response_generator(), media_type="application/x-ndjson")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============== CHAT HISTORY =================
@app.get("/chat/sessions", response_model=List[schemas.ChatSession])
def get_chat_sessions(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.ChatSession).filter(models.ChatSession.user_id == current_user.id).order_by(models.ChatSession.created_at.desc()).all()

@app.post("/chat/sessions", response_model=schemas.ChatSession)
def create_chat_session(session: schemas.ChatSessionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_session = models.ChatSession(user_id=current_user.id, title=session.title)
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

@app.get("/chat/sessions/{session_id}", response_model=List[schemas.ChatMessage])
def get_chat_messages(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id, models.ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session_id).order_by(models.ChatMessage.timestamp.asc()).all()

@app.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id, models.ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return {"status": "success"}

# ============== ADVANCED AGENTS (Chronicler & Strategist) ================

@app.get("/briefing/weekly", tags=["Advanced Agents"])
def get_weekly_briefing(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the Monday Morning Briefing from the Chronicler agent based on actual user data."""
    try:
        from agents.chronicler import ChroniclerAgent
        chronicler = ChroniclerAgent()
        briefing = chronicler.generate_monday_briefing(user_id=current_user.id)
        return {"briefing": briefing, "generated_at": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"briefing": f"Unable to generate briefing: {str(e)}", "generated_at": datetime.utcnow().isoformat()}

@app.get("/goals/me", tags=["Advanced Agents"])
def get_health_goals(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get active health goals for the user."""
    goals = db.query(models.HealthGoal).filter(
        models.HealthGoal.user_id == current_user.id
    ).order_by(models.HealthGoal.created_at.desc()).all()
    return goals

@app.post("/goals/me", tags=["Advanced Agents"])
def create_health_goal(
    goal: schemas.HealthGoalCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new health goal."""
    db_goal = models.HealthGoal(
        user_id=current_user.id,
        description=goal.description,
        status="active"
    )
    db.add(db_goal)
    db.commit()
    db.refresh(db_goal)
    return db_goal

@app.put("/goals/{goal_id}", tags=["Advanced Agents"])
def update_health_goal(
    goal_id: int,
    progress: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update goal progress."""
    goal = db.query(models.HealthGoal).filter(
        models.HealthGoal.id == goal_id,
        models.HealthGoal.user_id == current_user.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal.progress = min(progress, 100)
    if goal.progress >= 100:
        goal.status = "completed"
    db.commit()
    return goal

@app.get("/summaries/daily", tags=["Advanced Agents"])
def get_daily_summaries(
    days: int = 7,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get daily health summaries from the Chronicler."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    summaries = db.query(models.DailySummary).filter(
        models.DailySummary.user_id == current_user.id,
        models.DailySummary.date >= cutoff.date()
    ).order_by(models.DailySummary.date.desc()).all()
    return summaries

@app.post("/safety/check", tags=["Advanced Agents"])
def check_medication_safety(
    med_name: str,
    symptom: str,
    current_user: models.User = Depends(get_current_user)
):
    """Check if a symptom is a known side effect of a medication."""
    try:
        from agents.strategist import StrategistAgent
        strategist = StrategistAgent()
        result = strategist.check_medication_safety(med_name, symptom)
        return {"medication": med_name, "symptom": symptom, "result": result}
    except Exception as e:
        return {"medication": med_name, "symptom": symptom, "result": f"Error: {str(e)}"}

@app.post("/gamification/xp", tags=["Advanced Agents"])
def award_xp(
    task_name: str,
    current_user: models.User = Depends(get_current_user)
):
    """Award XP for completing a health task (Habitica integration)."""
    try:
        from agents.strategist import StrategistAgent
        strategist = StrategistAgent()
        result = strategist.award_habitica_xp(task_name)
        return {"task": task_name, "result": result}
    except Exception as e:
        return {"task": task_name, "result": f"Error: {str(e)}"}

# ============== OBSERVABILITY ================
@app.get("/observability/ping")
def ping():
    return {"status":"OK","monitoring":"active"}

@app.on_event("startup")
def startup_event():
    db = database.SessionLocal()
    try:
        if not db.query(models.User).first():
            print("Creating default user...")
            default_user = models.User(
                email="admin@aegis.com",
                hashed_password=get_password_hash("admin"),
                operating_mode=models.OperatingMode.PASSIVE
            )
            db.add(default_user)
            db.commit()
            print("Default user created: admin@aegis.com / admin")
    except Exception as e:
        print(f"Error creating default user: {e}")
    finally:
        db.close()

# ==============================================================================
# TWILIO VOICE WEBHOOK ENDPOINTS
# ==============================================================================

from fastapi import Form
from fastapi.responses import Response
import urllib.parse

@app.api_route("/twilio/voice/booking", methods=["GET", "POST"], tags=["Twilio Voice"])
async def twilio_voice_booking(
    request: Request,
    physician: str = None,
    time: str = None, 
    patient: str = None,
    callback: str = None
):
    """
    Twilio webhook - Interactive voice call with natural conversation.
    Uses Polly.Matthew (male) or Polly.Joanna (female) neural voices.
    """
    print(f"[TWILIO WEBHOOK] ======= BOOKING CALL STARTED =======")
    
    # Decode URL parameters
    physician = urllib.parse.unquote(physician or "the doctor")
    time = urllib.parse.unquote(time or "your earliest availability")
    patient = urllib.parse.unquote(patient or "a patient")
    callback = urllib.parse.unquote(callback or "")
    
    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "")
    
    # Build params for next step
    params = urllib.parse.urlencode({
        'physician': physician,
        'time': time,
        'patient': patient,
        'callback': callback
    })
    
    # Simple one-way message - no interaction
    message = f"""Hello, this is an automated call from AEGIS Health Assistant. 
    I am calling on behalf of {patient} to request an appointment with Doctor {physician}. 
    The preferred time is {time}. 
    {"Please call back at " + callback + " to confirm." if callback and callback != "not provided" else "Please confirm at your earliest convenience."}
    Thank you for your time. Goodbye."""
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">{message}</Say>
    <Hangup/>
</Response>"""
    
    print(f"[TWILIO WEBHOOK] Simple voice message sent")
    return Response(content=twiml, media_type="application/xml")


@app.api_route("/twilio/voice/conversation", methods=["GET", "POST"], tags=["Twilio Voice"])
async def twilio_voice_conversation(
    request: Request,
    physician: str = None,
    time: str = None, 
    patient: str = None,
    callback: str = None,
    step: int = 1
):
    """
    Handles the back-and-forth conversation during the booking call.
    Uses Gemini to generate contextual responses.
    """
    # Get SpeechResult or Digits from form data (Twilio sends as POST body)
    try:
        form_data = await request.form()
        SpeechResult = form_data.get("SpeechResult", "")
        Digits = form_data.get("Digits", "")
        # If they pressed a button, treat it as confirmation
        if Digits and not SpeechResult:
            SpeechResult = "Yes, this is the office" if Digits == "1" else f"Pressed {Digits}"
    except:
        SpeechResult = ""
        Digits = ""
    
    print(f"[TWILIO CONVERSATION] Step {step}, Speech: {SpeechResult}, Digits: {Digits}")
    
    physician = urllib.parse.unquote(physician or "the doctor")
    time = urllib.parse.unquote(time or "your earliest availability")
    patient = urllib.parse.unquote(patient or "a patient")
    callback = urllib.parse.unquote(callback or "")
    
    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "")
    
    # Use Gemini to generate a natural response
    ai_response = "Thank you for your time. We will follow up. Goodbye."
    
    if SpeechResult:
        try:
            from agents.llm_engine import generate_medical_response
            
            context = f"""You are an AI assistant on a phone call booking a medical appointment.
You are calling Doctor {physician}'s office on behalf of patient {patient}.
The patient wants an appointment at {time}.
{"The patient's callback number is " + callback if callback and callback != "not provided" else ""}

The person on the phone just said: "{SpeechResult}"

Generate a brief, natural phone response (1-2 sentences). Be polite and conversational.
- If they confirm availability, thank them and confirm the appointment.
- If they ask for more info, provide details about the patient and time.
- If they say the doctor is busy, ask about alternative times.
- If they seem confused, clarify that you're an AI assistant booking an appointment.
- End appropriately if the conversation is complete.

Keep it SHORT and natural for a phone call."""
            
            ai_response = generate_medical_response(context, max_tokens=100)
            ai_response = ai_response.strip().replace('"', '')
            print(f"[TWILIO] Gemini response: {ai_response}")
        except Exception as e:
            print(f"[TWILIO ERROR] Gemini failed: {e}")
            ai_response = "I apologize, I'm having trouble understanding. Could you please repeat that?"
    
    # Check if conversation should end
    end_keywords = ["goodbye", "bye", "thank you", "confirmed", "noted", "got it", "will call back"]
    should_end = any(kw in (SpeechResult or "").lower() for kw in end_keywords) or step >= 4
    
    params = urllib.parse.urlencode({
        'physician': physician,
        'time': time,
        'patient': patient,
        'callback': callback
    })
    
    voice = "alice"
    
    try:
        if should_end or "goodbye" in ai_response.lower() or "thank you" in ai_response.lower():
            # End the call
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{voice}">{ai_response}</Say>
    <Pause length="1"/>
    <Say voice="{voice}">Thank you for your time. Have a great day!</Say>
    <Hangup/>
</Response>"""
        else:
            # Continue conversation
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{voice}">{ai_response}</Say>
    <Gather input="dtmf speech" timeout="8" numDigits="1" action="/twilio/voice/conversation?{params}&amp;step={step+1}" method="POST"/>
    <Say voice="{voice}">I did not hear a response. Thank you for your time. Goodbye.</Say>
    <Hangup/>
</Response>"""
        
        print(f"[TWILIO CONVERSATION] Returning TwiML for step {step}")
        return Response(content=twiml, media_type="application/xml")
    except Exception as e:
        print(f"[TWILIO ERROR] Conversation failed: {e}")
        error_twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{voice}">I apologize, there was a technical issue. Please try again later. Goodbye.</Say>
    <Hangup/>
</Response>"""
        return Response(content=error_twiml, media_type="application/xml")


# Keep the old complex version as backup
@app.api_route("/twilio/voice/booking-advanced", methods=["GET", "POST"], tags=["Twilio Voice"])
async def twilio_voice_booking_advanced(
    request: Request,
    physician: str = None,
    time: str = None, 
    patient: str = None,
    callback: str = None
):
    """Advanced version with recording"""
    physician = urllib.parse.unquote(physician or "the doctor")
    time = urllib.parse.unquote(time or "your earliest availability")
    patient = urllib.parse.unquote(patient or "a patient")
    callback = urllib.parse.unquote(callback or "")
    
    booking_message = f"Hello, this is AEGIS Health Assistant calling on behalf of {patient} to request an appointment with {physician} at {time}."
    
    if callback and callback != "not provided":
        booking_message += f" Please call back at {callback} to confirm."
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{booking_message}</Say>
    <Pause length="2"/>
    <Say voice="Polly.Joanna">If you need to respond, please speak after the beep.</Say>
    <Record maxLength="30" transcribe="true"/>
    <Say voice="Polly.Joanna">
        Thank you. We will process your response.
    </Say>
    <Hangup/>
</Response>"""
    
    return Response(content=twiml, media_type="application/xml")

@app.post("/twilio/voice/respond", tags=["Twilio Voice"])
async def twilio_voice_respond(
    physician: str = None,
    patient: str = None,
    time: str = None,
    RecordingUrl: str = Form(None),
    TranscriptionText: str = Form(None),
    CallSid: str = Form(None),
    SpeechResult: str = Form(None)
):
    """
    Handles the physician's voice response during the booking call.
    Uses Gemini to generate an appropriate AI response.
    """
    print(f"[TWILIO] Voice response received - CallSid: {CallSid}")
    print(f"[TWILIO] Speech/Transcription: {SpeechResult or TranscriptionText}")
    
    response_text = SpeechResult or TranscriptionText or ""
    
    # Use Gemini to generate a contextual response
    ai_response = "Thank you for your response. We will notify the patient."
    
    if response_text:
        try:
            from agents.llm_engine import generate_medical_response
            
            prompt = f"""You are an AI assistant on a phone call booking a medical appointment.
The physician's office just responded: "{response_text}"
You were booking an appointment for {patient} with {physician} at {time}.

Generate a brief, polite phone response (1-2 sentences max). Be natural and conversational.
If they confirmed, say thank you. If they need more info, apologize and say the patient will call back."""
            
            ai_response = generate_medical_response(prompt, max_tokens=100)
            ai_response = ai_response.strip()
        except Exception as e:
            print(f"[TWILIO ERROR] Gemini response failed: {e}")
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-US">
        {ai_response}
    </Say>
    <Pause length="1"/>
    <Say voice="Polly.Joanna">
        Goodbye.
    </Say>
    <Hangup/>
</Response>"""
    
    return Response(content=twiml, media_type="application/xml")

@app.post("/twilio/voice/status", tags=["Twilio Voice"])
async def twilio_voice_status(
    CallSid: str = Form(None),
    CallStatus: str = Form(None),
    CallDuration: str = Form(None),
    RecordingUrl: str = Form(None)
):
    """
    Receives call status updates from Twilio.
    Logs the call progress and stores recording URL.
    """
    print(f"[TWILIO STATUS] CallSid: {CallSid}, Status: {CallStatus}, Duration: {CallDuration}s")
    
    if RecordingUrl:
        print(f"[TWILIO] Recording available: {RecordingUrl}")
        # TODO: Store recording URL in database for reference
    
    return {"status": "received", "call_sid": CallSid, "call_status": CallStatus}


# ==============================================================================
# EMERGENCY CONTACTS & EMERGENCY CALL ENDPOINTS
# ==============================================================================

from pydantic import BaseModel

class EmergencyContactCreate(BaseModel):
    name: str
    relationship: str  # spouse, parent, child, sibling, friend, physician
    phone_number: str  # E.164 format: +1234567890
    email: Optional[str] = None
    priority: int = 1  # 1 = first to call
    notify_on_critical: bool = True

class EmergencyContactResponse(BaseModel):
    id: int
    name: str
    relationship: str
    phone_number: str
    email: Optional[str]
    priority: int
    is_active: str
    notify_on_critical: str
    
    class Config:
        from_attributes = True


@app.get("/emergency/contacts", response_model=List[EmergencyContactResponse], tags=["Emergency"])
def get_emergency_contacts(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all emergency contacts for the current user."""
    contacts = db.query(models.EmergencyContact).filter(
        models.EmergencyContact.user_id == current_user.id
    ).order_by(models.EmergencyContact.priority).all()
    return contacts


@app.post("/emergency/contacts", response_model=EmergencyContactResponse, tags=["Emergency"])
def add_emergency_contact(
    contact: EmergencyContactCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a new emergency contact."""
    new_contact = models.EmergencyContact(
        user_id=current_user.id,
        name=contact.name,
        relationship=contact.relationship,
        phone_number=contact.phone_number,
        email=contact.email,
        priority=contact.priority,
        notify_on_critical="true" if contact.notify_on_critical else "false"
    )
    db.add(new_contact)
    db.commit()
    db.refresh(new_contact)
    return new_contact


@app.put("/emergency/contacts/{contact_id}", response_model=EmergencyContactResponse, tags=["Emergency"])
def update_emergency_contact(
    contact_id: int,
    contact: EmergencyContactCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing emergency contact."""
    existing = db.query(models.EmergencyContact).filter(
        models.EmergencyContact.id == contact_id,
        models.EmergencyContact.user_id == current_user.id
    ).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    existing.name = contact.name
    existing.relationship = contact.relationship
    existing.phone_number = contact.phone_number
    existing.email = contact.email
    existing.priority = contact.priority
    existing.notify_on_critical = "true" if contact.notify_on_critical else "false"
    
    db.commit()
    db.refresh(existing)
    return existing


@app.delete("/emergency/contacts/{contact_id}", tags=["Emergency"])
def delete_emergency_contact(
    contact_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an emergency contact."""
    existing = db.query(models.EmergencyContact).filter(
        models.EmergencyContact.id == contact_id,
        models.EmergencyContact.user_id == current_user.id
    ).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    db.delete(existing)
    db.commit()
    return {"status": "deleted", "id": contact_id}


@app.post("/emergency/call", tags=["Emergency"])
def trigger_emergency_call(
    reason: str = "Emergency assistance requested",
    current_user: models.User = Depends(get_current_user)
):
    """
    Manually trigger an emergency call to all emergency contacts.
    This will make real phone calls via Twilio.
    """
    try:
        from integrations.twilio_emergency import make_emergency_call, is_twilio_configured
        
        if not is_twilio_configured():
            raise HTTPException(
                status_code=503,
                detail="Emergency call system not configured. Please set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER environment variables."
            )
        
        result = make_emergency_call(
            user_id=current_user.id,
            reason=reason,
            trigger_type="user_request"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/emergency/call-logs", tags=["Emergency"])
def get_emergency_call_logs(
    limit: int = 20,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get history of emergency calls made for this user."""
    logs = db.query(models.EmergencyCallLog).filter(
        models.EmergencyCallLog.user_id == current_user.id
    ).order_by(models.EmergencyCallLog.timestamp.desc()).limit(limit).all()
    return logs


# ================== PHYSICIANS ENDPOINTS ==================

@app.get("/physicians/me", tags=["Physicians"])
def get_my_physicians(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all saved physicians for the current user."""
    physicians = db.query(models.Physician).filter(
        models.Physician.user_id == current_user.id
    ).order_by(models.Physician.name).all()
    return physicians


class PhysicianCreate(schemas.BaseModel):
    name: str
    specialty: Optional[str] = None
    clinic: Optional[str] = None
    phone: Optional[str] = None

@app.post("/physicians/me", tags=["Physicians"])
def add_physician(
    physician: PhysicianCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a new physician to the user's contacts."""
    new_physician = models.Physician(
        user_id=current_user.id,
        name=physician.name,
        specialty=physician.specialty,
        clinic=physician.clinic,
        phone=physician.phone
    )
    db.add(new_physician)
    db.commit()
    db.refresh(new_physician)
    return new_physician


@app.delete("/physicians/{physician_id}", tags=["Physicians"])
def delete_physician(
    physician_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a physician from the user's contacts."""
    existing = db.query(models.Physician).filter(
        models.Physician.id == physician_id,
        models.Physician.user_id == current_user.id
    ).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Physician not found")
    
    db.delete(existing)
    db.commit()
    return {"status": "deleted", "id": physician_id}


@app.post("/emergency/status", tags=["Emergency"])
async def emergency_call_status_webhook(
    CallSid: str = Form(None),
    CallStatus: str = Form(None),
    CallDuration: str = Form(None),
    RecordingUrl: str = Form(None)
):
    """
    Twilio webhook for emergency call status updates.
    Updates the call log with status changes.
    """
    print(f"[EMERGENCY STATUS] CallSid: {CallSid}, Status: {CallStatus}, Duration: {CallDuration}s")
    
    db = database.SessionLocal()
    try:
        call_log = db.query(models.EmergencyCallLog).filter(
            models.EmergencyCallLog.call_sid == CallSid
        ).first()
        
        if call_log:
            call_log.status = CallStatus
            if CallDuration:
                call_log.duration_seconds = int(CallDuration)
            if RecordingUrl:
                call_log.recording_url = RecordingUrl
            db.commit()
    finally:
        db.close()
    
    return {"status": "received"}


@app.post("/emergency/callback", tags=["Emergency"])
async def emergency_call_callback_webhook(
    Digits: str = Form(None),
    CallSid: str = Form(None)
):
    """
    Twilio webhook for when emergency contact presses a digit.
    1 = Acknowledge, 2 = Repeat message
    """
    print(f"[EMERGENCY CALLBACK] CallSid: {CallSid}, Digits: {Digits}")
    
    if Digits == "1":
        # Acknowledged
        db = database.SessionLocal()
        try:
            call_log = db.query(models.EmergencyCallLog).filter(
                models.EmergencyCallLog.call_sid == CallSid
            ).first()
            if call_log:
                call_log.status = "acknowledged"
                db.commit()
        finally:
            db.close()
        
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Thank you for confirming. Please check on the patient as soon as possible. Goodbye.</Say>
    <Hangup/>
</Response>"""
    elif Digits == "2":
        # Repeat - redirect to original
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Redirect>/emergency/repeat</Redirect>
</Response>"""
    else:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Invalid input. Press 1 to confirm or 2 to repeat.</Say>
    <Gather numDigits="1" action="/emergency/callback" method="POST"/>
</Response>"""
    
    return Response(content=twiml, media_type="application/xml")


# ================== WHATSAPP BOOKING ENDPOINTS ==================

@app.post("/whatsapp/webhook", tags=["WhatsApp"])
async def whatsapp_incoming_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(None),
    AccountSid: str = Form(None)
):
    """
    Twilio webhook for incoming WhatsApp messages.
    Handles responses from physician offices for appointment booking.
    """
    print(f"[WHATSAPP] Incoming from {From}: {Body[:100]}...")
    
    try:
        from integrations.twilio_whatsapp import process_incoming_message, generate_webhook_response
        
        result = process_incoming_message(From, Body)
        
        print(f"[WHATSAPP] Action: {result.get('action')}")
        
        # Generate TwiML response
        twiml_response = generate_webhook_response(result)
        
        return Response(content=twiml_response, media_type="application/xml")
        
    except Exception as e:
        print(f"[WHATSAPP ERROR] {e}")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )


@app.post("/whatsapp/status", tags=["WhatsApp"])
async def whatsapp_status_webhook(
    MessageSid: str = Form(None),
    MessageStatus: str = Form(None),
    To: str = Form(None),
    ErrorCode: str = Form(None),
    ErrorMessage: str = Form(None)
):
    """
    Twilio webhook for WhatsApp message status updates.
    """
    print(f"[WHATSAPP STATUS] {MessageSid}: {MessageStatus}")
    
    if ErrorCode:
        print(f"[WHATSAPP ERROR] Code: {ErrorCode}, Message: {ErrorMessage}")
    
    return {"status": "received"}


@app.get("/whatsapp/booking/{session_id}", tags=["WhatsApp"])
async def get_whatsapp_booking_status(
    session_id: str,
    current_user: models.User = Depends(get_current_user)
):
    """
    Get the status of a WhatsApp booking conversation.
    """
    try:
        from integrations.twilio_whatsapp import WhatsAppBookingSession
        
        session = WhatsAppBookingSession.get(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Booking session not found")
        
        if session["user_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        return {
            "session_id": session_id,
            "state": session["state"],
            "physician": session["physician_name"],
            "preferred_time": session["preferred_time"],
            "confirmed_time": session.get("confirmed_time"),
            "messages": session.get("messages", []),
            "created_at": session["created_at"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
