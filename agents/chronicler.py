from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, ChatSession, ChatMessage, HealthEvent, MedicalNote, DailySummary
from agents.llm_engine import generate_medical_response
from datetime import datetime, timedelta
import json

class ChroniclerAgent:
    def __init__(self):
        pass

    def summarize_day(self, user_id: int, date_str: str = None) -> str:
        """
        Aggregates all interactions and health events for a specific day and generates a summary.
        If date_str is None, defaults to today.
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
            
        print(f"[CHRONICLER] 📜 Summarizing day {date_str} for User {user_id}...")
        
        session = SessionLocal()
        try:
            # 1. Fetch Chat Sessions for the day
            chat_sessions = session.query(ChatSession).filter(
                ChatSession.user_id == user_id,
                ChatSession.created_at.like(f"{date_str}%")
            ).all()
            
            chat_text = ""
            for s in chat_sessions:
                chat_text += f"\nSession '{s.title}':\n"
                for m in s.messages:
                    chat_text += f"- {m.role}: {m.content}\n"

            # 2. Fetch Health Events
            events = session.query(HealthEvent).filter(
                HealthEvent.user_id == user_id,
                HealthEvent.timestamp.like(f"{date_str}%")
            ).all()
            
            event_text = ""
            for e in events:
                event_text += f"- {e.event_type}: {json.dumps(e.data)}\n"

            # 3. Fetch Medical Notes
            notes = session.query(MedicalNote).filter(
                MedicalNote.user_id == user_id,
                MedicalNote.date == date_str
            ).all()
            
            note_text = ""
            for n in notes:
                note_text += f"- Note by {n.provider}: {n.summary}\n"

            if not (chat_text or event_text or note_text):
                return "No activity recorded for this day."

            # 4. Generate Summary via LLM
            prompt = f"""
            You are the Chronicler, a medical AI responsible for summarizing a patient's daily health journey.
            
            DATE: {date_str}
            
            CHAT LOGS:
            {chat_text}
            
            HEALTH EVENTS:
            {event_text}
            
            MEDICAL NOTES:
            {note_text}
            
            TASK:
            1. Summarize the key health-related discussions, symptoms reported, and actions taken.
            2. Assess the patient's overall mood/sentiment (e.g., Anxious, Optimistic, Stable).
            3. Highlight any critical alerts or new diagnoses.
            
            OUTPUT FORMAT (JSON):
            {{
                "summary": "...",
                "mood": "..."
            }}
            """
            
            response = generate_medical_response(prompt, max_tokens=512)
            
            try:
                # Attempt to parse JSON
                clean_response = response.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_response)
                summary_text = data.get("summary", "No summary generated.")
                mood = data.get("mood", "Unknown")
            except:
                summary_text = response
                mood = "Unknown"

            # 5. Save to Database
            existing = session.query(DailySummary).filter(
                DailySummary.user_id == user_id,
                DailySummary.date == date_str
            ).first()
            
            if existing:
                existing.summary = summary_text
                existing.mood = mood
                print(f"[CHRONICLER] Updated existing summary.")
            else:
                new_summary = DailySummary(
                    user_id=user_id,
                    date=date_str,
                    summary=summary_text,
                    mood=mood
                )
                session.add(new_summary)
                print(f"[CHRONICLER] Created new summary.")
            
            session.commit()
            return f"Summary for {date_str}: {summary_text} (Mood: {mood})"

        except Exception as e:
            print(f"[CHRONICLER ERROR] {e}")
            return f"Error generating summary: {e}"
        finally:
            session.close()

    def analyze_signal(self, signal_data: list, sampling_rate: int = 100) -> dict:
        """
        Analyzes raw physiological signal (ECG/PPG) using NeuroKit2.
        Returns extracted features like Heart Rate Variability (HRV).
        """
        print(f"[CHRONICLER] 📈 Analyzing signal with NeuroKit2 ({len(signal_data)} points)...")
        try:
            import neurokit2 as nk
            import pandas as pd
            import numpy as np
            
            # Convert to numpy array
            signal = np.array(signal_data)
            
            # Process ECG (Simulated for now as we might get PPG or ECG)
            # We'll assume it's a clean PPG/ECG signal for this demo
            signals, info = nk.ecg_process(signal, sampling_rate=sampling_rate)
            
            # Extract features
            hrv_metrics = nk.hrv(info, sampling_rate=sampling_rate, show=False)
            
            # Extract key metrics
            mean_hr = signals["ECG_Rate"].mean()
            rmssd = hrv_metrics["HRV_RMSSD"].values[0]
            sdnn = hrv_metrics["HRV_SDNN"].values[0]
            
            analysis = {
                "mean_heart_rate": round(mean_hr, 1),
                "hrv_rmssd": round(rmssd, 1),
                "hrv_sdnn": round(sdnn, 1),
                "stress_level": "High" if rmssd < 20 else "Low" # Simple heuristic
            }
            
            print(f"[CHRONICLER] 📊 Analysis Result: {analysis}")
            return analysis
            
        except ImportError:
            return {"error": "NeuroKit2 not installed."}
        except Exception as e:
            print(f"[CHRONICLER ERROR] Signal analysis failed: {e}")
            return {"error": str(e)}

    def generate_monday_briefing(self, user_id: int) -> str:
        """
        Generates a weekly summary (Monday Morning Briefing) based on actual user data.
        Aggregates DailySummaries, HealthEvents, and chat interactions from the past 7 days.
        """
        print(f"[CHRONICLER] 📅 Generating Monday Briefing for User {user_id}...")
        
        session = SessionLocal()
        try:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=7)
            
            # 1. Fetch Daily Summaries from past week
            # Note: date column is VARCHAR, so compare as string
            cutoff_str = cutoff.strftime("%Y-%m-%d")
            summaries = session.query(DailySummary).filter(
                DailySummary.user_id == user_id,
                DailySummary.date >= cutoff_str
            ).order_by(DailySummary.date.desc()).all()
            
            # 2. Fetch Health Events (vitals) from past week
            events = session.query(HealthEvent).filter(
                HealthEvent.user_id == user_id,
                HealthEvent.timestamp >= cutoff
            ).all()
            
            # 3. Aggregate vitals data
            heart_rates = []
            spo2_values = []
            for e in events:
                if e.event_type == "vitals" and e.data:
                    if "heart_rate" in e.data:
                        heart_rates.append(e.data["heart_rate"])
                    if "spo2" in e.data:
                        spo2_values.append(e.data["spo2"])
            
            # Calculate stats
            avg_hr = sum(heart_rates) / len(heart_rates) if heart_rates else None
            avg_spo2 = sum(spo2_values) / len(spo2_values) if spo2_values else None
            
            # 4. Build briefing context
            summary_text = "\n".join([f"- {s.date}: {s.summary}" for s in summaries]) if summaries else "No daily summaries recorded."
            
            # 5. Generate briefing with LLM
            week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%b %d")
            
            prompt = f"""
You are a health coach generating a Monday Morning Briefing for a patient.

**Week of {week_start}**

DATA:
- Average Heart Rate: {f'{avg_hr:.0f} bpm' if avg_hr else 'No data'}
- Average SpO2: {f'{avg_spo2:.1f}%' if avg_spo2 else 'No data'}
- Total vitals readings: {len(heart_rates)}
- Daily Summaries: {summary_text}

Generate a brief, encouraging weekly health summary with 2-4 bullet points.
Focus on trends, achievements, and one actionable recommendation.
Use markdown formatting with **bold** for emphasis.
End with a short motivational closing message in *italics*.
If no data is available, acknowledge this and encourage the user to start tracking.
"""
            
            briefing_content = generate_medical_response(prompt, max_tokens=400)
            
            # Format the final briefing
            briefing = f"""### 🌅 Monday Morning Briefing
**Week of {week_start}**

{briefing_content}
"""
            return briefing
            
        except Exception as e:
            print(f"[CHRONICLER ERROR] Briefing generation failed: {e}")
            return f"""### 🌅 Monday Morning Briefing
**Week of {datetime.now().strftime('%b %d')}**

Unable to generate briefing at this time. Please ensure you have health data recorded.

*Start tracking your vitals to receive personalized insights!*
"""
        finally:
            session.close()
