from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, DailySummary, HealthGoal, Condition, Medication
from agents.llm_engine import generate_medical_response
from datetime import datetime, timedelta
import json

class StrategistAgent:
    def __init__(self):
        pass

    def generate_plan(self, user_id: int) -> str:
        """
        Analyzes the last 7 days of summaries and current profile to generate a health plan.
        """
        print(f"[STRATEGIST] ♟️ Generating Health Plan for User {user_id}...")
        
        session = SessionLocal()
        try:
            # 1. Fetch Recent Summaries (last 7 days)
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            summaries = session.query(DailySummary).filter(
                DailySummary.user_id == user_id,
                DailySummary.date >= seven_days_ago
            ).order_by(DailySummary.date.asc()).all()
            
            history_text = ""
            for s in summaries:
                history_text += f"- {s.date}: {s.summary} (Mood: {s.mood})\n"
                
            if not history_text:
                history_text = "No recent daily summaries available."

            # 2. Fetch Patient Profile
            conditions = session.query(Condition).filter(Condition.user_id == user_id).all()
            meds = session.query(Medication).filter(Medication.user_id == user_id).all()
            
            profile_text = "Conditions: " + ", ".join([c.name for c in conditions]) + "\n"
            profile_text += "Medications: " + ", ".join([m.name for m in meds])

            # 3. Fetch Active Goals
            goals = session.query(HealthGoal).filter(
                HealthGoal.user_id == user_id,
                HealthGoal.status == "active"
            ).all()
            
            goals_text = "\n".join([f"- {g.description}" for g in goals]) if goals else "None"

            # 4. Generate Plan via LLM
            prompt = f"""
            You are the Strategist, a medical AI planner.
            
            PATIENT PROFILE:
            {profile_text}
            
            RECENT HISTORY (Last 7 Days):
            {history_text}
            
            CURRENT GOALS:
            {goals_text}
            
            TASK:
            1. Analyze the trends in the patient's health and mood.
            2. Suggest 1-3 concrete, actionable Health Goals for the next week.
            3. Provide a brief motivational message.
            
            OUTPUT FORMAT (JSON):
            {{
                "analysis": "...",
                "new_goals": ["Goal 1", "Goal 2"],
                "message": "..."
            }}
            """
            
            response = generate_medical_response(prompt, max_tokens=512)
            
            try:
                clean_response = response.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_response)
                
                analysis = data.get("analysis", "")
                new_goals = data.get("new_goals", [])
                message = data.get("message", "")
                
                # 5. Save New Goals
                for goal_desc in new_goals:
                    # Check if similar goal exists to avoid duplicates (simple check)
                    existing = session.query(HealthGoal).filter(
                        HealthGoal.user_id == user_id,
                        HealthGoal.description.like(f"%{goal_desc[:10]}%") # Fuzzy match start
                    ).first()
                    
                    if not existing:
                        new_goal = HealthGoal(
                            user_id=user_id,
                            description=goal_desc,
                            status="active"
                        )
                        session.add(new_goal)
                        print(f"[STRATEGIST] Set new goal: {goal_desc}")
                
                session.commit()
                
                return f"**Analysis**: {analysis}\n\n**New Goals Set**:\n" + "\n".join([f"- {g}" for g in new_goals]) + f"\n\n**Message**: {message}"
                
            except Exception as e:
                return f"Error parsing plan: {e}. Raw response: {response}"

        except Exception as e:
            return f"Error generating plan: {e}"
        finally:
            session.close()

    def award_habitica_xp(self, task_name: str, difficulty: str = "easy") -> str:
        """
        Awards XP via Habitica API (Mocked for now).
        """
        print(f"[STRATEGIST] 🎮 Awarding XP for: {task_name} ({difficulty})")
        # In production: requests.post("https://habitica.com/api/v3/user/tasks/...", headers=...)
        xp = 10 if difficulty == "easy" else 50
        return f"Level Up! You gained {xp} XP for completing '{task_name}'."

    def check_context_intervention(self, heart_rate: int, calendar_event: str) -> str:
        """
        Checks if an intervention is needed based on physiological and contextual data.
        Example: High HR during a meeting -> Stress intervention.
        """
        print(f"[STRATEGIST] 🧠 Checking Context: HR={heart_rate}, Event='{calendar_event}'")
        
        if heart_rate > 100 and "meeting" in calendar_event.lower():
            return "⚠️ High stress detected during your meeting. Take 3 deep breaths. (Context-Aware Intervention)"
            
        if heart_rate < 60 and "gym" in calendar_event.lower():
            return "⚠️ Your heart rate is too low for a workout. Push harder! (Context-Aware Intervention)"
            
        return "No intervention needed."

    def check_medication_safety(self, med_name: str, symptom: str) -> str:
        """
        Checks OpenFDA for adverse events.
        """
        from agents.knowledge import check_adverse_events, check_specific_reaction
        
        # 1. Check specific pair first (More accurate)
        count = check_specific_reaction(med_name, symptom)
        if count > 0:
             return f"⚠️ CAUTION: '{symptom}' is a reported side effect of {med_name} ({count} reports found)."
        
        # 2. Fallback: Check top events (Broad check)
        events = check_adverse_events(med_name, limit=5)
        for e in events:
            if symptom.lower() in e['reaction'].lower():
                return f"⚠️ CAUTION: '{symptom}' is a known side effect of {med_name} (Reported {e['count']} times)."
                
        return f"'{symptom}' does not appear to be a common side effect of {med_name} in the FDA database."
