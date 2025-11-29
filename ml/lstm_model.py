import numpy as np

# In a real scenario, this would import torch and load a trained model.
# For this restored version, we use a heuristic based on clinical thresholds.

def predict_risk(sequence):
    """
    Predicts risk score (0-1) from a sequence of vitals.
    sequence: numpy array of shape (seq_len, 6)
    Features: [heartrate, resprate, o2sat, sbp, dbp, temperature]
    """
    if not isinstance(sequence, np.ndarray):
        return 0.1

    # Extract features (assuming the order matches the docstring in sentinel.py)
    # [heartrate, resprate, o2sat, sbp, dbp, temperature]
    try:
        hr = sequence[:, 0]
        spo2 = sequence[:, 2]
        sbp = sequence[:, 3]
        
        # Clinical Logic Heuristics
        risk_score = 0.1
        
        # Critical thresholds
        if np.any(hr > 120) or np.any(hr < 40):
            risk_score = max(risk_score, 0.9)
        if np.any(spo2 < 90):
            risk_score = max(risk_score, 0.95)
        if np.any(sbp > 180) or np.any(sbp < 90):
            risk_score = max(risk_score, 0.85)
            
        # Warning thresholds
        if np.any(hr > 100) or np.any(spo2 < 95):
            risk_score = max(risk_score, 0.65)
            
        return risk_score
    except Exception:
        return 0.1
