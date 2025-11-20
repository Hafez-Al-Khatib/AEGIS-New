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