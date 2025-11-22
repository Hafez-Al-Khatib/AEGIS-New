from fastapi import FastAPI, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import time

import models, schemas, database, influx_ingester
from observability import log_api_call, log_agent_event
from alert_engine import evaluate_vitals, evaluate_sentinel_output
from prometheus_fastapi_instrumentator import Instrumentator
from metrics import AGENT_CALLS, AGENT_LATENCY

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

# ================== UTILS ====================
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str):
    return pwd_context.hash(password)

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

# ============== VITALS + ALERTS =============
@app.post("/vitals/me")
def log_vitals(vitals: schemas.VitalsLog,
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):

    influx_ingester.write_vitals(
        user_id=current_user.id,
        heart_rate=vitals.heart_rate,
        spo2=vitals.spo2
    )

    alert, message = evaluate_vitals(
        vitals.heart_rate,
        vitals.spo2
    )

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

        return {"status": "ALERT", "message": message}

    return {"status": "success"}

@app.get("/alerts/me", response_model=List[schemas.Alert])
def get_alerts(db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):

    return db.query(models.Alert)\
             .filter(models.Alert.user_id==current_user.id)\
             .order_by(models.Alert.timestamp.desc()).all()


# ============== ANALYZE DOCUMENT ============
@app.post("/analyze/document", tags=["Agents"])
async def analyze_document(
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
        data = ingestor.extract_medical_data(temp)
        AGENT_LATENCY.labels("Ingestor").observe(time.perf_counter() - t0)

        AGENT_CALLS.labels("Sentinel").inc()
        t1 = time.perf_counter()
        analysis = sentinel.analyze_health_record(data,
                          f"User: {current_user.email}")
        AGENT_LATENCY.labels("Sentinel").observe(time.perf_counter() - t1)

        alert, reason = evaluate_sentinel_output(analysis)

        if alert:
            db_alert = models.Alert(
                user_id=current_user.id,
                message=reason,
                severity="HIGH"
            )
            db.add(db_alert)
            db.commit()
            log_agent_event("Sentinel", current_user.id,
                            "ALERT_FROM_DOCUMENT",
                            (time.perf_counter()-t1)*1000,
                            {"reason": reason})

            return {"status":"ALERT","reason":reason}

        return {"status": "success", "analysis": analysis}

    finally:
        if os.path.exists(temp):
            os.remove(temp)

# ============== OBSERVABILITY ================
@app.get("/observability/ping")
def ping():
    return {"status":"OK","monitoring":"active"}
