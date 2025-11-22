from agents.llm_engine import generate_medical_response
import json

class SentinelAgent:
    def analyze_health_record(self, extracted_data: dict, user_context: str = ""):
        """
        Analyzes the structured JSON from the Ingestor using Meditron.
        """
        # Convert the dict back to a pretty string for the LLM to read
        data_str = json.dumps(extracted_data, indent=2)
        
        prompt = f"""
        You are an expert medical AI assistant. Analyze these lab results for a patient.

        PATIENT CONTEXT:
        {user_context}

        LAB RESULTS:
        {data_str}

        INSTRUCTIONS:
        1. Identify any values that are outside the reference range.
        2. Explain what these abnormalities might indicate.
        3. Suggest 3 safe, actionable next steps.
        4. Add a disclaimer that you are an AI.

        ANALYSIS:
        """
        
        # We increase max_tokens here because analysis requires more text than a simple chat
        response = generate_medical_response(prompt, max_tokens=400)
        return response

# Singleton instance
sentinel = SentinelAgent()

from ml.lstm_model import predict_risk

def assess_risk_from_vitals(sequence):
    risk = predict_risk(sequence)

    if risk > 0.85:
        return risk, "HIGH"
    elif risk > 0.6:
        return risk, "MEDIUM"
    else:
        return risk, "LOW"
# sentinel_risk.py (example)
import numpy as np
from ml.lstm_model import predict_risk

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
