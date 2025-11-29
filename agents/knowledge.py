import requests
import json

# ==============================================================================
# KNOWLEDGE BASE: LOINC (Labs), RxNorm (Meds), OpenFDA (Safety)
# ==============================================================================

def normalize_loinc(lab_name: str) -> dict:
    """
    Normalizes a lab test name to its LOINC code using the LOINC API (or a subset).
    For this demo, we use a local lookup for common tests to ensure reliability without an API key.
    """
    # Common LOINC codes mapping (Demo Subset)
    # In production, this would query the official LOINC FHIR API
    loinc_map = {
        "glucose": {"code": "2345-7", "name": "Glucose [Mass/volume] in Serum or Plasma"},
        "blood sugar": {"code": "2345-7", "name": "Glucose [Mass/volume] in Serum or Plasma"},
        "hba1c": {"code": "4548-4", "name": "Hemoglobin A1c/Hemoglobin.total in Blood"},
        "a1c": {"code": "4548-4", "name": "Hemoglobin A1c/Hemoglobin.total in Blood"},
        "systolic": {"code": "8480-6", "name": "Systolic blood pressure"},
        "diastolic": {"code": "8462-4", "name": "Diastolic blood pressure"},
        "heart rate": {"code": "8867-4", "name": "Heart rate"},
        "spo2": {"code": "59408-5", "name": "Oxygen saturation in Arterial blood by Pulse oximetry"},
    }
    
    key = lab_name.lower().strip()
    if key in loinc_map:
        return loinc_map[key]
    
    # Fallback: Return unknown but structured
    return {"code": "UNKNOWN", "name": lab_name}

def normalize_rxnorm(med_name: str) -> dict:
    """
    Normalizes a medication name to its RxNorm CUI using the NIH RxNorm API.
    """
    print(f"[KNOWLEDGE] 💊 Normalizing Medication: {med_name}")
    try:
        base_url = "https://rxnav.nlm.nih.gov/REST/rxcui.json"
        params = {"name": med_name}
        response = requests.get(base_url, params=params, timeout=5)
        data = response.json()
        
        # Parse response
        id_group = data.get("idGroup", {})
        if "rxnormId" in id_group:
            rxcui = id_group["rxnormId"][0]
            return {"rxcui": rxcui, "name": med_name}
            
        return {"rxcui": None, "name": med_name, "error": "Not found"}
        
    except Exception as e:
        print(f"[KNOWLEDGE ERROR] RxNorm failed: {e}")
        return {"rxcui": None, "name": med_name, "error": str(e)}

def check_adverse_events(med_name: str, limit: int = 5) -> list:
    """
    Queries OpenFDA to find reported adverse events for a medication.
    Useful for the Strategist to check safety.
    """
    print(f"[KNOWLEDGE] ⚠️ Checking Adverse Events for: {med_name}")
    try:
        base_url = "https://api.fda.gov/drug/event.json"
        # Query for patient.drug.medicinalproduct containing the med name
        # and count the patient.reaction.reactionmeddrapt (reaction terms)
        query = f'patient.drug.medicinalproduct:"{med_name}"'
        params = {
            "search": query,
            "count": "patient.reaction.reactionmeddrapt.exact",
            "limit": limit
        }
        
        response = requests.get(base_url, params=params, timeout=5)
        data = response.json()
        
        results = []
        if "results" in data:
            for item in data["results"]:
                results.append({"reaction": item["term"], "count": item["count"]})
                
        return results
        
    except Exception as e:
        print(f"[KNOWLEDGE ERROR] OpenFDA failed: {e}")
        return []

def check_specific_reaction(med_name: str, reaction: str) -> int:
    """
    Queries OpenFDA to check if a specific reaction is reported for a medication.
    Returns the count of reports.
    """
    print(f"[KNOWLEDGE] 🔎 Checking if '{reaction}' is a side effect of '{med_name}'")
    try:
        base_url = "https://api.fda.gov/drug/event.json"
        # Query for both drug and specific reaction
        # We use .exact to be precise, but for user queries we might want partial match.
        # Let's try a broad search first.
        query = f'patient.drug.medicinalproduct:"{med_name}" AND patient.reaction.reactionmeddrapt:"{reaction}"'
        params = {
            "search": query,
            "limit": 1
        }
        
        response = requests.get(base_url, params=params, timeout=5)
        data = response.json()
        
        if "meta" in data and "results" in data["meta"]:
            return data["meta"]["results"]["total"]
            
        return 0
        
    except Exception as e:
        # 404 means no results found usually
        if "404" in str(e) or (response.status_code == 404):
            return 0
        print(f"[KNOWLEDGE ERROR] OpenFDA specific check failed: {e}")
        return 0

if __name__ == "__main__":
    # Simple test
    print(normalize_loinc("Glucose"))
    print(normalize_rxnorm("Tylenol"))
    print(check_adverse_events("Tylenol"))
