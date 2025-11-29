from agents.graph import app
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import json
from ml.lstm_model import predict_risk
import numpy as np
from agents.llm_engine import generate_medical_response

class SentinelAgent:
    
    def analyze_health_record(self, extracted_data: dict, user_context: str = ""):
        """
        Analyzes the health record using the Sentinel 2.0 LangGraph workflow.
        """
        print("[SENTINEL] Starting analysis via LangGraph...")
        
        # Convert extracted data to string format
        if isinstance(extracted_data, dict):
            medical_record_str = json.dumps(extracted_data, indent=2)
        else:
            medical_record_str = str(extracted_data)
            
        # Initialize State
        initial_state = {
            "messages": [],
            "medical_record": medical_record_str,
            "user_context": user_context,
            "iterations": 0
        }
        
        # Run Graph
        try:
            final_state = app.invoke(initial_state)
            messages = final_state['messages']
            
            # Format Output for Frontend
            final_output = ""
            
            for msg in messages:
                if isinstance(msg, AIMessage):
                    final_output += f"{msg.content}\n\n"
                elif isinstance(msg, SystemMessage):
                    # Format tool results as [System] blocks for frontend parsing
                    if "Tool Result" in msg.content:
                        content = msg.content
                        if "Physician" in content:
                            final_output += f"**[System] Physician Discovery:** {content}\n\n"
                        else:
                            final_output += f"**[System] Tool Result:** {content}\n\n"
                            
            return final_output.strip()
            
        except Exception as e:
            print(f"[SENTINEL ERROR] Graph execution failed: {e}")
            return f"Error during analysis: {e}"

    def extract_structured_data(self, text: str) -> dict:
        """
        ETL: Extracts structured entities (Meds, Conditions, Allergies) from text.
        Returns a JSON object.
        """
        print("[SENTINEL] 🏗️ Extracting structured data from medical record...")
        
        prompt = f"""
        You are a Medical ETL (Extract, Transform, Load) Agent.
        
        TASK: Extract structured medical data from the following text.
        
        TEXT:
        {text}
        
        OUTPUT FORMAT (JSON ONLY):
        {{
            "medications": [
                {{"name": "drug name", "dosage": "e.g. 500mg", "frequency": "e.g. daily", "status": "Active"}}
            ],
            "conditions": [
                {{"name": "diagnosis", "diagnosis_date": "YYYY-MM-DD or Unknown", "status": "Active/Chronic/Resolved"}}
            ],
            "allergies": [
                {{"allergen": "substance", "reaction": "reaction description", "severity": "Mild/Moderate/Severe"}}
            ],
            "lab_results": [
                {{"test_name": "e.g. Glucose", "value": "105", "unit": "mg/dL", "reference_range": "70-100", "date": "YYYY-MM-DD"}}
            ],
            "medical_notes": [
                {{"date": "YYYY-MM-DD", "provider": "Dr. Name", "note_text": "Full text or key excerpt", "summary": "Brief summary of the visit/note"}}
            ]
        }}
        
        RULES:
        1. Only extract EXPLICITLY mentioned items.
        2. If a field is missing, use null or "Unknown".
        3. Return ONLY valid JSON. No markdown formatting.
        """
        
        try:
            response = generate_medical_response(prompt, max_tokens=8192)
            # Clean response (remove markdown code blocks if present)
            clean_json = response.replace("```json", "").replace("```", "").strip()
            import json
            data = json.loads(clean_json)
            print(f"[SENTINEL] Extracted: {len(data.get('medications', []))} meds, {len(data.get('lab_results', []))} labs.")
            return data
        except Exception as e:
            print(f"[SENTINEL ERROR] ETL failed: {e}")
            return {}

    def chat(self, query: str, history: list = [], user_context: str = "", user_id: int = None, user_location: dict = None):
        """
        Handles conversational queries using the same LangGraph workflow.
        """
        print(f"[SENTINEL] Chat query from user {user_id}: {query}")
        
        # Initialize State
        # For chat, the 'medical_record' might be empty or just the query context
        # We pass the query as a HumanMessage in the messages list
        
        initial_messages = []
        # Reconstruct history
        for msg in history:
            if msg.get("role") == "user":
                initial_messages.append(HumanMessage(content=msg.get("content")))
            elif msg.get("role") == "assistant":
                initial_messages.append(AIMessage(content=msg.get("content")))
                
        # Add current query
        initial_messages.append(HumanMessage(content=query))
        
        initial_state = {
            "messages": initial_messages,
            "medical_record": "No active medical record for this chat session. Refer to Knowledge Base if needed.",
            "user_context": user_context + (f" | User ID: {user_id}" if user_id else ""),
            "iterations": 0,
            "user_id": user_id,  # Add user_id to state for tool access`n            "user_location": user_location or {}  # Browser geolocation
        }
        
        try:
            final_state = app.invoke(initial_state)
            messages = final_state['messages']
            
            # Get the last AI message
            last_message = messages[-1]
            if isinstance(last_message, AIMessage):
                return last_message.content
            else:
                return "I'm not sure how to respond to that."
                
        except Exception as e:
            print(f"[SENTINEL ERROR] Chat execution failed: {e}")
            return f"Error during chat: {e}"

# Singleton instance
sentinel = SentinelAgent()

def assess_risk_from_vitals(sequence):
    risk = predict_risk(sequence)

    if risk > 0.85:
        return risk, "HIGH"
    elif risk > 0.6:
        return risk, "MEDIUM"
    else:
        return risk, "LOW"

def compute_risk_from_vitals_window(vitals_df, max_steps=32):
    """
    vitals_df: pandas DataFrame with columns:
      ['heartrate','resprate','o2sat','sbp','dbp','temperature']
      for a single stay_id, sorted by time.
    """
    features = ["heartrate","resprate","o2sat","sbp","dbp","temperature"]
    seq = vitals_df[features].values

    # same padding/truncation as training
    if len(seq) >= max_steps:
        seq = seq[:max_steps]
    else:
        pad = np.zeros((max_steps - len(seq), len(features)))
        seq = np.vstack([seq, pad])

    risk = predict_risk(seq)

    if risk > 0.85:
        level = "HIGH"
    elif risk > 0.6:
        level = "MEDIUM"
    else:
        level = "LOW"

    return risk, level
