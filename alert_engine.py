def evaluate_vitals(heart_rate, spo2):
    if heart_rate > 120 or heart_rate < 40:
        return True, f"Critical heart rate: {heart_rate}"
    if spo2 < 90:
        return True, f"Critical SpO2: {spo2}"
    return False, ""

def evaluate_sentinel_output(analysis):
    # Simple heuristic: if analysis contains "urgent" or "immediate attention"
    if isinstance(analysis, str):
        lower_analysis = analysis.lower()
        if "urgent" in lower_analysis or "immediate attention" in lower_analysis:
            return True, "Sentinel detected urgent condition"
    return False, ""
