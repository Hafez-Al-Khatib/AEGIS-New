from agents.llm_engine import generate_medical_response
from agents.hospital_service import hospital_manager, EmergencySeverity
from agents.ingestor import vision_agent
import json
from typing import Dict, Optional, Tuple, List

class SentinelAgent:
    def __init__(self):
        """Initialize Sentinel with emergency detection thresholds"""
        self.critical_indicators = [
            "cardiac arrest",
            "stroke",
            "sepsis",
            "anaphylaxis",
            "severe bleeding",
            "respiratory failure",
            "severe trauma",
            "coma"
        ]
        self.high_risk_values = {
            "heart_rate": {"min": 40, "max": 120},
            "spo2": {"min": 90},
            "blood_pressure_systolic": {"max": 180},
            "temperature": {"min": 35.0, "max": 40.0}  # Celsius; < 35°C or > 40°C is critical
        }
    
    def detect_emergency_severity(self, extracted_data: dict) -> Tuple[str, bool, str]:
        """
        Analyze extracted medical data for emergency severity
        
        Args:
            extracted_data: Structured medical data from vision agent
            
        Returns:
            Tuple of (severity_level, is_emergency, reason)
        """
        data_str = json.dumps(extracted_data, indent=2).lower()
        
        # Check for critical indicators
        for indicator in self.critical_indicators:
            if indicator in data_str:
                return EmergencySeverity.CRITICAL, True, f"Critical condition detected: {indicator}"
        
        # Check for high-risk vital values
        if isinstance(extracted_data, dict):
            vitals = extracted_data.get("vitals", {})
            
            if isinstance(vitals, dict):
                hr = vitals.get("heart_rate")
                spo2 = vitals.get("spo2")
                sys_bp = vitals.get("blood_pressure_systolic")
                temp = vitals.get("temperature")
                
                if hr and (hr < self.high_risk_values["heart_rate"]["min"] or 
                          hr > self.high_risk_values["heart_rate"]["max"]):
                    return EmergencySeverity.HIGH, True, f"Abnormal heart rate: {hr} bpm"
                
                if spo2 and spo2 < self.high_risk_values["spo2"]["min"]:
                    return EmergencySeverity.HIGH, True, f"Low oxygen saturation: {spo2}%"
                
                if sys_bp and sys_bp > self.high_risk_values["blood_pressure_systolic"]["max"]:
                    return EmergencySeverity.HIGH, True, f"Elevated blood pressure: {sys_bp} mmHg"
                
                if temp and (temp < self.high_risk_values["temperature"]["min"] or 
                            temp > self.high_risk_values["temperature"]["max"]):
                    return EmergencySeverity.HIGH, True, f"Critical temperature: {temp}°C"
        
        return EmergencySeverity.LOW, False, "No emergency indicators detected"
    
    def analyze_health_record(self, extracted_data: dict, user_context: str = "", 
                             user_id: Optional[int] = None,
                             user_email: Optional[str] = None,
                             user_location: Optional[Dict] = None) -> Dict:
        """
        Analyzes the structured JSON from the Ingestor using Meditron.
        Also detects emergency conditions and initiates hospital contact if needed.
        
        Args:
            extracted_data: Structured medical data
            user_context: Patient context information
            user_id: User ID for emergency logging
            user_email: User email for emergency contact
            user_location: User's location (lat, lon) for nearest hospital
            
        Returns:
            Dictionary with analysis, emergency status, and hospital info
        """
        # Convert the dict back to a pretty string for the LLM to read
        data_str = json.dumps(extracted_data, indent=2) if not isinstance(extracted_data, str) else extracted_data

        # Detect emergency severity
        severity, is_emergency, emergency_reason = self.detect_emergency_severity(extracted_data)

        # Retrieve patient history summaries from memory (if available)
        patient_history_entries: List[str] = []
        if user_id is not None:
            try:
                docs = vision_agent.search_memory(str(user_id), search_type="patient")
                # take up to 5 most recent summaries
                for d in docs[-5:]:
                    s = d.get("summary") or d.get("content")
                    patient_history_entries.append(f"- {s}")
            except Exception:
                patient_history_entries = []

        patient_history_str = "\n".join(patient_history_entries) if patient_history_entries else "No prior documents available."

        prompt = f"""
        You are an expert medical AI assistant. Analyze these lab results and patient documents for a patient.

        PATIENT CONTEXT:
        {user_context}

        PATIENT HISTORY (summaries from ingested documents):
        {patient_history_str}

        LAB RESULTS / DOCUMENT CONTENT:
        {data_str}

        INSTRUCTIONS:
        1. Identify any values that are outside the reference range.
        2. Explain what these abnormalities might indicate.
        3. Suggest 3 safe, actionable next steps.
        4. Add a disclaimer that you are an AI.

        ANALYSIS:
        """

        # We include patient history as memory to the LLM wrapper so it can use context
        response = generate_medical_response(prompt, max_tokens=400, memory=patient_history_entries)
        
        result = {
            "analysis": response,
            "severity_level": severity,
            "is_emergency": is_emergency,
            "emergency_reason": emergency_reason
        }
        
        # If emergency detected and we have user info, initiate hospital contact
        if is_emergency and user_id and user_email:
            result["emergency_contact"] = self._initiate_emergency_contact(
                user_id=user_id,
                user_email=user_email,
                severity=severity,
                medical_summary=emergency_reason,
                user_location=user_location
            )
        
        return result
    
    def _initiate_emergency_contact(self, user_id: int, user_email: str, 
                                   severity: str, medical_summary: str,
                                   user_location: Optional[Dict] = None) -> Dict:
        """
        Internal method to initiate emergency hospital contact
        
        Args:
            user_id: User ID
            user_email: User email
            severity: Emergency severity level
            medical_summary: Summary of medical issue
            user_location: User location dict with 'latitude' and 'longitude'
            
        Returns:
            Emergency contact result
        """
        latitude = None
        longitude = None
        
        if user_location:
            latitude = user_location.get("latitude")
            longitude = user_location.get("longitude")
        
        return hospital_manager.call_emergency_services(
            user_id=user_id,
            user_email=user_email,
            severity=severity,
            medical_summary=medical_summary,
            latitude=latitude,
            longitude=longitude
        )

# Singleton instance
sentinel = SentinelAgent()