# AEGIS Setup Guide

Complete guide for setting up the AEGIS health monitoring system.

---

## Table of Contents

1. [Quick Start (Docker)](#quick-start-docker)
2. [Local Development Setup](#local-development-setup)
3. [API Keys & Credentials](#api-keys--credentials)
4. [LLM Configuration](#llm-configuration)
5. [Database Setup](#database-setup)
6. [Troubleshooting](#troubleshooting)

---

## Quick Start (Docker)

The fastest way to get AEGIS running is with Docker:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/aegis.git
cd aegis

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env with your API keys (see below)
nano .env  # or use your preferred editor

# 4. Build and start all services
docker-compose up --build

# 5. Access the application
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
```

---

## Local Development Setup

### Prerequisites

- Python 3.11+ 
- Node.js 18+
- PostgreSQL (optional, SQLite works for development)
- CUDA-capable GPU (optional, for local LLM)

### Backend Setup

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your keys
# Then start the server
uvicorn main:app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

---

## API Keys & Credentials

### Required Keys

| Service | Environment Variable | How to Get |
|---------|---------------------|------------|
| **Google API** | `GOOGLE_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |

### Optional Keys (Enable More Features)

| Service | Environment Variable | Purpose | How to Get |
|---------|---------------------|---------|------------|
| **Twilio** | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | Emergency calls & WhatsApp | [Twilio Console](https://console.twilio.com) |
| **Google Maps** | `GOOGLE_MAPS_API_KEY` | Find nearby facilities | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| **Google Calendar** | `credentials.json` | Schedule appointments | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| **Habitica** | `HABITICA_USER_ID`, `HABITICA_API_TOKEN` | Gamification | [Habitica Settings](https://habitica.com/user/settings/api) |

---

### Setting Up Each Service

#### 1. Google Gemini API (Required for Beta Mode)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click "Create API Key"
3. Copy the key and add to `.env`:
   ```
   GOOGLE_API_KEY=your_key_here
   USE_GEMINI_BETA=true
   ```

#### 2. Twilio (Emergency Calls & WhatsApp)

1. Create account at [Twilio](https://www.twilio.com/try-twilio)
2. Get your Account SID and Auth Token from the [Console](https://console.twilio.com)
3. Buy a phone number with Voice capabilities
4. For WhatsApp, enable the [WhatsApp Sandbox](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
5. Add to `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_PHONE_NUMBER=+1234567890
   TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
   ```

6. Configure webhooks in Twilio Console:
   - Voice webhook: `https://your-domain.com/voice/booking`
   - WhatsApp webhook: `https://your-domain.com/whatsapp/webhook`
   
   For local development, use [ngrok](https://ngrok.com):
   ```bash
   ngrok http 8000
   # Then set AEGIS_BASE_URL to your ngrok URL
   ```

#### 3. Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable "Google Calendar API"
4. Create OAuth 2.0 credentials (Desktop App)
5. Download as `credentials.json` and place in project root
6. On first run, you'll be prompted to authenticate

#### 4. Google Maps API

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Enable "Places API" and "Geocoding API"
3. Create an API key
4. Add to `.env`:
   ```
   GOOGLE_MAPS_API_KEY=your_key_here
   ```

#### 5. Habitica (Gamification)

1. Log in to [Habitica](https://habitica.com)
2. Go to Settings → API
3. Copy User ID and API Token
4. Add to `.env`:
   ```
   HABITICA_USER_ID=your_user_id
   HABITICA_API_TOKEN=your_api_token
   ```

---

## LLM Configuration

AEGIS supports two LLM modes:

### Option 1: Qwen 2.5 7B (Privacy Mode - Default)

Runs completely locally. No data leaves your system.

1. Download the model:
   ```bash
   # Create models directory
   mkdir -p agents/models
   
   # Download from Hugging Face (requires ~8GB)
   # Option A: Using huggingface-cli
   huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
     qwen2.5-7b-instruct-q8_0.gguf \
     --local-dir agents/models
   
   # Option B: Direct download
   wget https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q8_0.gguf \
     -O agents/models/qwen2.5-7b-instruct.gguf
   ```

2. Set environment:
   ```
   LLM_PROVIDER=qwen
   USE_GEMINI_BETA=false
   QWEN_MODEL_PATH=agents/models/qwen2.5-7b-instruct.gguf
   ```

### Option 2: Gemini 2.0 Flash (Beta Mode)

Uses Google's cloud API. Faster but requires internet.

```
LLM_PROVIDER=gemini
USE_GEMINI_BETA=true
GOOGLE_API_KEY=your_key_here
```

---

## Database Setup

### SQLite (Default - Development)

No setup needed. Database file `aegis.db` is created automatically.

### PostgreSQL (Production)

1. Create database:
   ```sql
   CREATE DATABASE aegis;
   CREATE USER aegis_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE aegis TO aegis_user;
   ```

2. Set environment:
   ```
   DATABASE_URL=postgresql://aegis_user:your_password@localhost:5432/aegis
   ```

### InfluxDB (Time-Series Vitals)

Used for high-frequency vitals data.

1. Install InfluxDB 2.x
2. Create organization and bucket
3. Generate API token
4. Set environment:
   ```
   INFLUX_URL=http://localhost:8086
   INFLUX_TOKEN=your_token
   INFLUX_ORG=aegis_org
   INFLUX_BUCKET=vitals
   MOCK_INFLUX=false
   ```

---

## Environment File Template

Create `.env` in project root:

```bash
# ============== REQUIRED ==============
SECRET_KEY=generate-a-secure-random-key-here

# ============== LLM (Choose One) ==============
# Option 1: Local Qwen (Privacy Mode)
LLM_PROVIDER=qwen
USE_GEMINI_BETA=false
QWEN_MODEL_PATH=agents/models/qwen2.5-7b-instruct.gguf

# Option 2: Gemini Cloud (Beta Mode)
# LLM_PROVIDER=gemini
# USE_GEMINI_BETA=true
# GOOGLE_API_KEY=your_key

# ============== OPTIONAL SERVICES ==============
# Twilio (Emergency Calls)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
TWILIO_WHATSAPP_NUMBER=
AEGIS_BASE_URL=http://localhost:8000

# Google Services
GOOGLE_MAPS_API_KEY=

# Habitica
HABITICA_USER_ID=
HABITICA_API_TOKEN=

# ============== DATABASE ==============
# Leave empty for SQLite (default)
# DATABASE_URL=postgresql://user:pass@localhost:5432/aegis

# InfluxDB (optional)
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=
INFLUX_ORG=aegis_org
INFLUX_BUCKET=vitals
MOCK_INFLUX=true
```

---

## Troubleshooting

### Common Issues

#### "Form is not defined" error
```bash
# This is fixed - ensure you have the latest code
git pull
```

#### NumPy version conflict
```bash
pip install numpy<2
```

#### CUDA not found (for local LLM)
```bash
# Install CUDA toolkit from NVIDIA
# Or use CPU mode (slower):
pip install llama-cpp-python --force-reinstall
```

#### Port already in use
```bash
# Find and kill process on port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# Linux/Mac
lsof -i :8000
kill -9 <pid>
```

#### Docker build fails
```bash
# Clear Docker cache and rebuild
docker-compose down -v
docker system prune -f
docker-compose up --build
```

---

## Next Steps

After setup is complete:

1. Access the dashboard at `http://localhost:5173`
2. Register a new account
3. Start chatting with the AI agent
4. Connect your Galaxy Watch (see [GALAXY_WATCH_INTEGRATION.md](GALAXY_WATCH_INTEGRATION.md))
5. Add emergency contacts in the dashboard

For feature details, see [FEATURES_SHOWCASE.md](FEATURES_SHOWCASE.md).
