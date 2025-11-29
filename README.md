# AEGIS

## Agentic Environment for Guardian Intelligence in Healthcare Systems

<p align="center">
  <img src="docs/images/aegis-logo.png" alt="AEGIS Logo" width="200"/>
</p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Latest-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![React](https://img.shields.io/badge/React-18+-blue.svg)](https://reactjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

---

## 🎯 Overview

AEGIS is a **multi-agent AI health monitoring system** that goes beyond simple chatbots to provide:

- 🚨 **Autonomous Emergency Response** - Real phone calls via Twilio when vitals are critical
- ⌚ **Real-Time Vitals Monitoring** - Samsung Galaxy Watch 4 integration
- 🤖 **Multi-Agent Architecture** - Sentinel, Chronicler, and Strategist agents collaborate
- 🎙️ **AI Voice Calls** - Book appointments through actual phone calls
- 🧬 **Lifestyle Optimization** - Personalized health plans with clinical evidence
- 🔐 **Privacy-First** - Local LLM option (Qwen 2.5 7B) keeps data on-device

> **This is not "just retrieval and booking"** - see [FEATURES_SHOWCASE.md](docs/FEATURES_SHOWCASE.md) for a detailed breakdown of advanced capabilities.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AEGIS SYSTEM                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   SENTINEL   │  │  CHRONICLER  │  │  STRATEGIST  │          │
│  │   (Triage)   │  │  (Vitals)    │  │  (Actions)   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│                    ┌───────▼────────┐                           │
│                    │   LANGGRAPH    │                           │
│                    │  State Machine │                           │
│                    └───────┬────────┘                           │
│                            │                                     │
│  ┌────────────────────────┼────────────────────────┐           │
│  │                        │                         │           │
│  ▼                        ▼                         ▼           │
│ ┌────────┐          ┌──────────┐            ┌────────────┐     │
│ │ Qwen   │          │ Twilio   │            │ Google     │     │
│ │ 2.5 7B │          │ Voice    │            │ Maps/Cal   │     │
│ └────────┘          └──────────┘            └────────────┘     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                     DATA LAYER                                   │
│  ┌────────────┐   ┌────────────┐   ┌────────────────────────┐  │
│  │ PostgreSQL │   │  InfluxDB  │   │   Galaxy Watch Data    │  │
│  │ (Records)  │   │ (Vitals)   │   │   (Health Connect)     │  │
│  └────────────┘   └────────────┘   └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Option 1: Docker (Recommended for Assessment)

```bash
# Clone the repository
git clone https://github.com/your-repo/aegis.git
cd aegis

# Copy environment template
cp .env.example .env

# Edit .env with your API keys (see Configuration section)
nano .env

# Start all services
docker-compose up --build

# Access the application
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
```

### Option 2: Local Development

```bash
# Backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

---

## ⚙️ Configuration

### Required Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_API_KEY` | Gemini API (beta mode only) | For Gemini |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | For voice calls |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | For voice calls |
| `TWILIO_PHONE_NUMBER` | Your Twilio number | For voice calls |
| `GOOGLE_MAPS_API_KEY` | Google Maps API | For location |

### LLM Options

```bash
# Privacy Mode (Default) - Runs locally
LLM_PROVIDER=qwen
USE_GEMINI_BETA=false

# Beta Mode - Uses Gemini API
LLM_PROVIDER=gemini
USE_GEMINI_BETA=true
GOOGLE_API_KEY=your_key_here
```

---

## 📱 Galaxy Watch Integration

### Option 1: Health Sync App (Recommended)

1. Install [Health Sync](https://play.google.com/store/apps/details?id=nl.appyhapps.healthsync) on your phone
2. Connect your Galaxy Watch 4
3. Configure webhook to send to AEGIS:

```
URL: http://your-server:8000/health-connect/webhook
Method: POST
API Key: aegis-health-key (or your custom key)
```

### Option 2: CSV Import (For Testing)

```bash
# Use sample vitals data
python scripts/ingest_vitals_csv.py --file data/sample_vitals.csv

# Or simulate real-time data
python scripts/simulate_vitals.py --interval 30
```

See [GALAXY_WATCH_INTEGRATION.md](docs/GALAXY_WATCH_INTEGRATION.md) for detailed setup.

---

## 🧪 Testing the System

### Demo Scenarios

1. **Emergency Response**
   ```
   User: "My heart rate is 160 and I'm having chest pain"
   AEGIS: [Triggers emergency call to contacts]
   ```

2. **Voice Appointment Booking**
   ```
   User: "Call Dr. Smith at +961-71-123456 to book Friday 3pm"
   AEGIS: [Makes actual phone call via Twilio]
   ```

3. **Health Analysis**
   ```
   User: "Give me my Monday morning briefing"
   AEGIS: [Returns 7-day health summary with trends]
   ```

### Test with Simulated Data

```bash
# Start vitals simulator (sends data every 30 seconds)
docker-compose --profile testing up vitals_simulator

# Or manually trigger critical vitals
curl -X POST http://localhost:8000/vitals/me \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"heart_rate": 165, "spo2": 85}'
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [SETUP_GUIDE.md](docs/SETUP_GUIDE.md) | **Complete setup instructions & API keys** |
| [FEATURES_SHOWCASE.md](docs/FEATURES_SHOWCASE.md) | Detailed feature breakdown (read this!) |
| [GALAXY_WATCH_INTEGRATION.md](docs/GALAXY_WATCH_INTEGRATION.md) | Watch setup guide |
| [.env.example](.env.example) | Environment variables template |

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** - High-performance API framework
- **LangGraph** - Multi-agent state machine orchestration
- **Qwen 2.5 7B** - Local privacy-preserving LLM
- **Gemini 2.0 Flash** - Optional cloud LLM (beta)
- **PostgreSQL** - Primary database
- **InfluxDB** - Time-series vitals storage
- **Twilio** - Voice calls and SMS

### Frontend
- **React 18** - UI framework
- **Tailwind CSS** - Styling
- **Recharts** - Data visualization
- **Lucide Icons** - Icon library

### Integrations
- Google Maps API (location services)
- Google Calendar API (scheduling)
- OpenFDA (drug safety)
- MedlinePlus (medical information)
- PubMed (research papers)
- Habitica (gamification)

---

## 🔐 Privacy & Security

- **Local LLM Option**: Qwen 2.5 7B runs entirely on-device
- **No Cloud Dependency**: System works offline (except for external APIs)
- **Encrypted Storage**: All sensitive data encrypted at rest
- **JWT Authentication**: Secure API access
- **HIPAA Considerations**: Architecture designed for healthcare compliance

---

## 📊 Key Differentiators

| Feature | Basic Health Chatbot | AEGIS |
|---------|---------------------|-------|
| Answer questions | ✅ | ✅ |
| Book appointments | Text only | **+ AI Voice Calls** |
| Real-time vitals | ❌ | ✅ Galaxy Watch |
| Emergency calls | ❌ | ✅ **Autonomous Twilio** |
| Multi-agent system | ❌ | ✅ LangGraph |
| Local LLM | ❌ | ✅ Qwen 2.5 7B |
| ECG Analysis | ❌ | ✅ NeuroKit2 |
| Gamification | ❌ | ✅ Habitica |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) & [LangGraph](https://github.com/langchain-ai/langgraph) for the agent framework
- [Qwen](https://github.com/QwenLM/Qwen) for the local LLM
- [MedlinePlus](https://medlineplus.gov/) for medical information
- [Twilio](https://www.twilio.com/) for voice capabilities

---

<p align="center">
  <strong>AEGIS - Because healthcare AI should do more than just answer questions.</strong>
</p>
