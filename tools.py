import os
import requests
from langchain.tools import tool
from database import SessionLocal
import models
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from twilio.rest import Client
from datetime import datetime, timedelta

# ==============================================================================
# GENERAL & UTILITY TOOLS
# ==============================================================================

@tool
def search_medical_knowledge(query: str) -> str:
    """
    Searches for medical information using PubMed API.
    Useful for finding symptoms, treatments, and general medical knowledge.
    """
    print(f"[TOOL] 🔎 Searching PubMed for: {query}")
    try:
        # Use PubMed E-utilities API
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # Step 1: Search for IDs
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmax": 3,
            "retmode": "json"
        }
        search_resp = requests.get(search_url, params=search_params, timeout=10)
        search_data = search_resp.json()
        
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return "No PubMed articles found for this query."
        
        # Step 2: Fetch summaries
        summary_url = f"{base_url}esummary.fcgi"
        summary_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }
        summary_resp = requests.get(summary_url, params=summary_params, timeout=10)
        summary_data = summary_resp.json()
        
        results = []
        for pmid in id_list:
            article = summary_data.get("result", {}).get(pmid, {})
            title = article.get("title", "No title")
            source = article.get("source", "")
            pubdate = article.get("pubdate", "")
            results.append(f"- **{title}** ({source}, {pubdate})\n  PMID: {pmid}\n")
        
        return "\n".join(results)
    except Exception as e:
        print(f"[TOOL ERROR] {e}")
        return f"Error searching PubMed: {e}"

# ==============================================================================
# LLM QUERY REFORMULATION HELPERS
# ==============================================================================

def reformulate_specialty(user_input: str) -> str:
    """
    Converts colloquial doctor references to proper medical specialty names.
    Uses LLM for complex cases, fast lookup for common ones.
    """
    # Fast lookup for common colloquial terms
    common_mappings = {
        "heart doctor": "Cardiologist",
        "heart specialist": "Cardiologist",
        "eye doctor": "Ophthalmologist",
        "skin doctor": "Dermatologist",
        "bone doctor": "Orthopedic surgeon",
        "brain doctor": "Neurologist",
        "kidney doctor": "Nephrologist",
        "lung doctor": "Pulmonologist",
        "stomach doctor": "Gastroenterologist",
        "children doctor": "Pediatrician",
        "kids doctor": "Pediatrician",
        "baby doctor": "Pediatrician",
        "women doctor": "Gynecologist",
        "pregnancy doctor": "Obstetrician",
        "mental health": "Psychiatrist",
        "therapist": "Psychologist",
        "foot doctor": "Podiatrist",
        "ear doctor": "ENT specialist",
        "cancer doctor": "Oncologist",
        "blood doctor": "Hematologist",
        "hormone doctor": "Endocrinologist",
        "allergy doctor": "Allergist",
        "joint doctor": "Rheumatologist",
        "nerve doctor": "Neurologist",
        "surgery": "General surgeon",
        "family doctor": "General practitioner",
        "gp": "General practitioner",
    }
    
    # Check fast lookup first
    user_lower = user_input.lower().strip()
    if user_lower in common_mappings:
        result = common_mappings[user_lower]
        print(f"[REFORMULATE] 🔄 '{user_input}' → '{result}' (fast lookup)")
        return result
    
    # If already looks like a specialty, return as-is
    specialty_keywords = ['ologist', 'iatrist', 'surgeon', 'specialist', 'physician', 'doctor']
    if any(kw in user_lower for kw in specialty_keywords):
        return user_input
    
    # Use LLM for complex/unknown terms
    from agents.llm_engine import generate_medical_response
    prompt = f"""Convert this to a medical specialty name for Google Maps search.

Input: "{user_input}"

Rules:
- Output ONLY the specialty name (e.g., "Cardiologist", "Orthopedic surgeon")
- If already a valid specialty, return it unchanged
- Use standard medical specialty terms

Output:"""
    
    try:
        response = generate_medical_response(prompt, max_tokens=20)
        result = response.strip().split('\n')[0].strip()
        if result and len(result) < 50:
            print(f"[REFORMULATE] 🧠 '{user_input}' → '{result}' (LLM)")
            return result
    except Exception as e:
        print(f"[REFORMULATE] LLM failed: {e}")
    
    return user_input


def reformulate_medical_history_query(query: str) -> list:
    """
    Converts user queries to medical record keywords.
    Returns list of terms to search in medical history.
    """
    # Fast lookup for common synonyms
    synonym_map = {
        "sugar": ["glucose", "blood sugar", "HbA1c", "diabetes"],
        "blood sugar": ["glucose", "HbA1c", "diabetes"],
        "heart rate": ["pulse", "HR", "heart rate", "cardiac"],
        "blood pressure": ["BP", "hypertension", "systolic", "diastolic"],
        "weight": ["weight", "BMI", "obesity"],
        "cholesterol": ["lipid", "LDL", "HDL", "triglycerides"],
        "kidney": ["renal", "creatinine", "GFR", "kidney"],
        "liver": ["hepatic", "ALT", "AST", "liver"],
        "thyroid": ["TSH", "T3", "T4", "thyroid"],
        "iron": ["ferritin", "hemoglobin", "anemia", "iron"],
    }
    
    query_lower = query.lower()
    for key, synonyms in synonym_map.items():
        if key in query_lower:
            print(f"[REFORMULATE] 🔄 History search: '{query}' → {synonyms}")
            return synonyms + [query]
    
    # For complex queries, use LLM
    from agents.llm_engine import generate_medical_response
    prompt = f"""Convert this patient query to medical record search terms.

Query: "{query}"

Rules:
- Output 2-4 medical terms that might appear in health records
- Include medical abbreviations and synonyms
- One term per line

Output:"""
    
    try:
        response = generate_medical_response(prompt, max_tokens=50)
        terms = [t.strip() for t in response.strip().split('\n') if t.strip() and len(t.strip()) < 40]
        if terms:
            print(f"[REFORMULATE] 🧠 History search: '{query}' → {terms}")
            return terms[:4] + [query]
    except Exception as e:
        print(f"[REFORMULATE] LLM failed: {e}")
    
    return [query]


def reformulate_facility_type(user_input: str) -> str:
    """
    Converts colloquial facility names to Google Maps search terms.
    """
    # Fast lookup
    mappings = {
        "drug store": "pharmacy",
        "drugstore": "pharmacy",
        "chemist": "pharmacy",
        "er": "hospital emergency room",
        "emergency room": "hospital emergency room",
        "urgent care": "urgent care clinic",
        "doctor office": "medical clinic",
        "clinic": "medical clinic",
        "lab": "medical laboratory",
        "blood test": "medical laboratory",
        "x-ray": "radiology center",
        "mri": "radiology center",
        "scan": "radiology center",
        "dentist": "dental clinic",
        "teeth": "dental clinic",
        "eye": "optical clinic",
        "glasses": "optical clinic",
    }
    
    user_lower = user_input.lower().strip()
    if user_lower in mappings:
        result = mappings[user_lower]
        print(f"[REFORMULATE] Facility: '{user_input}' → '{result}'")
        return result
    
    return user_input


def reformulate_query_for_medlineplus(query: str) -> list:
    """
    Uses LLM to convert a user query into MedlinePlus-friendly search terms.
    Returns a list of 1-3 canonical medical terms.
    """
    from agents.llm_engine import generate_medical_response
    
    prompt = f"""Convert this medical query into 1-3 simple MedlinePlus search terms.
MedlinePlus uses simple condition names, not complex phrases.

Query: "{query}"

Rules:
- Output ONLY the search terms, one per line
- Use simple medical terms (e.g., "arrhythmia" not "cardiac arrhythmia management")
- Remove words like: management, treatment, therapy, symptoms, strategies, guidelines
- For specific conditions, use the broader category if needed (e.g., "ventricular tachycardia" → "tachycardia" or "arrhythmia")
- Maximum 3 terms

Examples:
- "ventricular tachycardia management" → tachycardia\narrhythmia
- "type 2 diabetes treatment strategies" → diabetes
- "hypertension lifestyle modifications" → high blood pressure
- "myocardial infarction prevention" → heart attack

Output search terms only:"""

    try:
        response = generate_medical_response(prompt, max_tokens=50)
        # Parse response into list of terms
        terms = [t.strip() for t in response.strip().split('\n') if t.strip()]
        # Filter out any explanatory text
        terms = [t for t in terms if len(t) < 50 and not t.startswith('-')]
        return terms[:3] if terms else [query]
    except Exception as e:
        print(f"[TOOL] Query reformulation failed: {e}")
        return [query]

@tool
def search_clinical_guidance(query: str) -> str:
    """
    Searches MedlinePlus for patient-friendly clinical guidance.
    Returns actionable health information about conditions, treatments, and management.
    Better than PubMed for patient-facing advice.
    """
    import xml.etree.ElementTree as ET
    import re
    
    def search_medlineplus(search_term: str, db: str = "healthTopics") -> list:
        """Helper to search MedlinePlus with given term and database."""
        base_url = "https://wsearch.nlm.nih.gov/ws/query"
        params = {"db": db, "term": search_term, "retmax": 5}
        
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        results = []
        for doc in root.findall('.//document'):
            title = ""
            snippet = ""
            url = doc.get('url', '')
            
            for content in doc.findall('content'):
                name = content.get('name', '')
                if name == 'title':
                    title_text = content.text or ""
                    title = re.sub(r'<[^>]+>', '', title_text)  # Clean HTML from title
                elif name == 'FullSummary':
                    snippet = content.text or ""
                    # Clean all HTML tags and entities
                    snippet = re.sub(r'<[^>]+>', '', snippet)
                    snippet = re.sub(r'&[a-zA-Z]+;', '', snippet)  # Remove &nbsp; etc
                    snippet = re.sub(r'\s+', ' ', snippet).strip()  # Normalize whitespace
                    if len(snippet) > 800:
                        snippet = snippet[:800] + "..."
                elif name == 'snippet' and not snippet:
                    snippet = content.text or ""
                    snippet = re.sub(r'<[^>]+>', '', snippet)  # Clean HTML from snippet too
            
            if title:
                result_text = f"### {title}\n{snippet}\n"
                if url:
                    result_text += f"📖 [Read more]({url})\n"
                results.append(result_text)
        
        return results
    
    print(f"[TOOL] 🏥 Searching MedlinePlus for: {query}")
    
    try:
        results = []
        
        # Strategy 1: Use LLM to reformulate query into MedlinePlus-friendly terms
        reformulated_terms = reformulate_query_for_medlineplus(query)
        print(f"[TOOL] LLM reformulated to: {reformulated_terms}")
        
        for term in reformulated_terms:
            results = search_medlineplus(term, "healthTopics")
            if results:
                print(f"[TOOL] Found results for: {term}")
                break
        
        # Strategy 2: If LLM reformulation failed, try exact query
        if not results:
            results = search_medlineplus(query, "healthTopics")
        
        # Strategy 3: Try with 'all' database using reformulated terms
        if not results:
            print(f"[TOOL] Trying general MedlinePlus database...")
            for term in reformulated_terms:
                results = search_medlineplus(term, "all")
                if results:
                    break
        
        # Strategy 4: Fallback - simple word removal
        if not results:
            simplified = query
            remove_words = ['management', 'treatment', 'therapy', 'symptoms', 'causes', 
                          'prevention', 'lifestyle', 'strategies', 'guidelines', 'advice']
            for word in remove_words:
                simplified = re.sub(rf'\b{word}\b', '', simplified, flags=re.IGNORECASE)
            simplified = ' '.join(simplified.split())
            
            if simplified and simplified != query:
                print(f"[TOOL] Fallback simplified query: {simplified}")
                results = search_medlineplus(simplified, "healthTopics")
        
        if not results:
            return f"No clinical guidance found for '{query}'. This may be a specialized topic - consult your healthcare provider."
        
        return "**MedlinePlus Clinical Guidance:**\n\n" + "\n".join(results)
        
    except Exception as e:
        print(f"[TOOL ERROR] MedlinePlus search failed: {e}")
        return f"Error searching MedlinePlus: {e}"

def get_location_from_ip() -> tuple:
    """
    Get approximate location from IP address using free IP geolocation service.
    Returns (lat, lon, city) or (None, None, None) if failed.
    """
    try:
        response = requests.get("http://ip-api.com/json/", timeout=5)
        data = response.json()
        if data.get("status") == "success":
            lat = data.get("lat")
            lon = data.get("lon")
            city = data.get("city", "Unknown")
            country = data.get("country", "")
            print(f"[TOOL] 📍 IP Geolocation: {city}, {country} ({lat}, {lon})")
            return lat, lon, city
    except Exception as e:
        print(f"[TOOL WARNING] IP geolocation failed: {e}")
    return None, None, None

@tool
def locate_nearest_facility(lat: float = 0.0, lon: float = 0.0, facility_type: str = "hospital", city: str = None) -> str:
    """
    Finds the nearest medical facility using Google Places API.
    Priority: 1) Browser coordinates (lat/lon), 2) City geocoding, 3) IP geolocation, 4) Beirut default
    facility_type can be: hospital, pharmacy, doctor, dentist, clinic
    Returns list of nearby facilities with navigation links.
    """
    # Reformulate facility type for better search results
    reformulated_type = reformulate_facility_type(facility_type)
    print(f"[TOOL] 📍 Locating nearest {reformulated_type}...")
    
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY not found in environment variables."
    
    # Priority 1: Use browser coordinates if valid (non-zero)
    if lat != 0 and lon != 0:
        print(f"[TOOL] 📍 Using browser location: ({lat}, {lon})")
    # Priority 2: Geocode from city name
    elif city:
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="aegis_health_agent", timeout=5)
            # Add Lebanon context for better geocoding accuracy
            search_query = f"{city}, Lebanon" if "lebanon" not in city.lower() else city
            location = geolocator.geocode(search_query)
            if location:
                lat, lon = location.latitude, location.longitude
                print(f"[TOOL] 📍 Geocoded '{search_query}' to ({lat}, {lon})")
            else:
                print(f"[TOOL WARNING] Could not geocode '{search_query}'")
        except Exception as e:
            print(f"[TOOL WARNING] Geocoding failed: {e}")
    
    # Priority 3: IP geolocation fallback
    if lat == 0 and lon == 0:
        ip_lat, ip_lon, ip_city = get_location_from_ip()
        if ip_lat and ip_lon:
            lat, lon = ip_lat, ip_lon
            print(f"[TOOL] 📍 Using IP-detected location: {ip_city} ({lat}, {lon})")
    
    # Priority 4: Final fallback to Beirut
    if lat == 0 and lon == 0:
        lat, lon = 33.8938, 35.5018  # Beirut
        print(f"[TOOL] ⚠️ No location available, defaulting to Beirut")
        
    try:
        # Normalize to Google Places types (only 4 medical types available)
        # Google Places API only supports: hospital, pharmacy, doctor, dentist
        facility_lower = reformulated_type.lower()
        
        if "pharma" in facility_lower or "drug" in facility_lower or "medication" in facility_lower:
            place_type = "pharmacy"
        elif "dentist" in facility_lower or "dental" in facility_lower:
            place_type = "dentist"
        elif "doctor" in facility_lower or "physician" in facility_lower or "gp" in facility_lower or "clinic" in facility_lower:
            place_type = "doctor"
        elif "lab" in facility_lower or "radiology" in facility_lower:
            place_type = "hospital"  # Labs often associated with hospitals
        else:
            # Default: hospital covers clinics, medical centers, emergency, urgent care, etc.
            place_type = "hospital"
        
        print(f"[TOOL] 📍 Searching for '{place_type}' (from '{facility_type}' → '{reformulated_type}')")
        
        # Google Places API (New) - Nearby Search
        url = "https://places.googleapis.com/v1/places:searchNearby"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.currentOpeningHours,places.nationalPhoneNumber"
        }
        
        payload = {
            "includedTypes": [place_type],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": 5000.0
                }
            }
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        
        # Check for errors
        if "error" in data:
            error = data["error"]
            error_msg = error.get("message", "Unknown error")
            print(f"[TOOL ERROR] Google Places API: {error_msg}")
            return f"⚠️ Google Places API error: {error_msg}"
        
        results = data.get("places", [])
        print(f"[TOOL DEBUG] Places API returned {len(results)} results")
        
        if not results:
            return f"No {facility_type} found within 5km of the location."
        
        formatted = []
        for i, place in enumerate(results, 1):
            name = place.get("displayName", {}).get("text", "Unknown")
            print(f"[TOOL DEBUG] Place {i}: {name}")
            address = place.get("formattedAddress", "No address")
            rating = place.get("rating", "N/A")
            phone = place.get("nationalPhoneNumber", "")
            
            # Check if open
            is_open = place.get("currentOpeningHours", {}).get("openNow")
            open_status = "🟢 Open" if is_open else ("🔴 Closed" if is_open is False else "")
            
            # Get place location for navigation link
            location = place.get("location", {})
            place_lat = location.get("latitude", lat)
            place_lon = location.get("longitude", lon)
            
            # Google Maps navigation link
            nav_link = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={place_lat},{place_lon}&travelmode=driving"
            
            entry = f"{i}. **{name}** ({rating}⭐) {open_status}\n   📍 {address}"
            if phone:
                entry += f"\n   📞 {phone}"
            entry += f"\n   🧭 [Navigate]({nav_link})"
            
            formatted.append(entry)
        
        result = f"Found {len(results)} nearby {facility_type}s:\n\n" + "\n\n".join(formatted)
        print(f"[TOOL DEBUG] Full result length: {len(result)} chars")
        print(f"[TOOL DEBUG] Result preview: {result[:500]}...")
        return result
        
    except Exception as e:
        print(f"[TOOL ERROR] {e}")
        return f"Error locating facility: {e}"

@tool
def add_calendar_event(summary: str, start_time: str, end_time: str, email: str = None) -> str:
    """
    Adds an event to Google Calendar.
    Requires 'credentials.json' for Google OAuth/Service Account.
    start_time and end_time should be in ISO format (e.g., '2023-10-27T10:00:00').
    """
    print(f"[TOOL] 🗓️ Adding Calendar Event: {summary} ({start_time})")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        # For simplicity in this demo, we'll check for a service account file
        # In a real user-facing app, we'd use OAuth 2.0 flow with user consent.
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        SERVICE_ACCOUNT_FILE = 'd:\\Aegis\\credentials.json'
        
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            return "Google Calendar credentials not found. Event NOT added (SIMULATION)."
            
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)

        service = build('calendar', 'v3', credentials=creds)

        event = {
            'summary': summary,
            'description': 'Booked via Aegis Health Agent',
            'start': {
                'dateTime': start_time,
                'timeZone': 'UTC', # Adjust as needed
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'UTC',
            },
        }
        
        # 'primary' calendar of the service account or impersonated user
        # If using service account without domain-wide delegation, it only accesses its own calendar.
        # We'll assume we share the calendar with the service account or use it as a placeholder.
        event = service.events().insert(calendarId='primary', body=event).execute()
        
        return f"Event created: {event.get('htmlLink')}"
        
    except ImportError:
        return "Google API libraries not installed."
    except Exception as e:
        print(f"[TOOL ERROR] Calendar add failed: {e}")
        return f"Error adding to calendar: {e}"

# ==============================================================================
# PATIENT & PHYSICIAN TOOLS
# ==============================================================================

@tool
def search_my_physicians(query: str) -> str:
    """
    Searches the user's PERSONAL address book (database) for a physician.
    Use this FIRST before searching online if the user asks about 'my doctor' or if a name matches.
    """
    print(f"[TOOL] 📇 Searching My Physicians DB for: {query}")
    session = SessionLocal()
    try:
        # Simple case-insensitive search
        physicians = session.query(models.Physician).filter(models.Physician.name.ilike(f"%{query}%")).all()
        
        if not physicians:
            return "No matching physician found in your personal contacts."
            
        result = "Found in your contacts:\n"
        for p in physicians:
            result += f"- {p.name} ({p.specialty}) at {p.clinic}. Phone: {p.phone}\n"
        return result
    except Exception as e:
        return f"Database error: {e}"
    finally:
        session.close()

@tool
def search_physician(name: str, clinic: str = "") -> str:
    """
    Searches for a physician's contact info - checks database first, then suggests web search.
    Useful for finding profiles of doctors mentioned in reports.
    """
    print(f"[TOOL] 🔎 Searching for Physician: {name} at {clinic}")
    
    # First check personal database
    personal_result = search_my_physicians(name)
    if "Found in your contacts:" in personal_result:
        return personal_result
    
    # Return suggestion for manual search
    return f"Physician '{name}' not found in your personal contacts. Suggest searching online directories or contacting {clinic} directly for contact information."

@tool
def save_physician_contact(name: str, specialty: str, clinic: str, phone: str, user_id: int = None) -> str:
    """
    Saves a new physician's contact information to the user's personal address book (database).
    Use this when the user wants to 'save' a doctor found online.
    """
    print(f"[TOOL] 💾 Saving Physician: {name} ({specialty})")
    session = SessionLocal()
    try:
        # Check if already exists
        existing = session.query(models.Physician).filter(
            models.Physician.name == name, 
            models.Physician.user_id == user_id
        ).first()
        
        if existing:
            return f"Physician '{name}' is already in your contacts."
            
        new_physician = models.Physician(
            user_id=user_id,
            name=name,
            specialty=specialty,
            clinic=clinic,
            phone=phone
        )
        session.add(new_physician)
        session.commit()
        return f"Successfully saved Dr. {name} to your personal contacts."
    except Exception as e:
        return f"Database error: {e}"
    finally:
        session.close()

@tool
def find_providers_online(specialty: str, location: str = "", lat: float = 0.0, lon: float = 0.0) -> str:
    """
    Searches for medical providers using Google Places API (New).
    Returns structured contact info (Name, Address, Phone, Rating) with navigation links.
    Priority: Browser coordinates > City geocoding > IP geolocation > Beirut default
    """
    # Reformulate specialty for better search results
    reformulated_specialty = reformulate_specialty(specialty)
    print(f"[TOOL] 🩺 Searching for: {reformulated_specialty}")
    
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY not found in environment variables."
    
    # Priority 1: Use browser coordinates if valid
    if lat != 0 and lon != 0:
        print(f"[TOOL] 📍 Using browser location: ({lat}, {lon})")
    # Priority 2: Geocode from location name
    elif location:
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="aegis_provider_search", timeout=5)
            search_query = f"{location}, Lebanon" if "lebanon" not in location.lower() else location
            loc_data = geolocator.geocode(search_query)
            if loc_data:
                lat, lon = loc_data.latitude, loc_data.longitude
                print(f"[TOOL] 📍 Geocoded '{search_query}' to ({lat}, {lon})")
        except Exception as e:
            print(f"[TOOL WARNING] Geocoding failed: {e}")
    
    # Priority 3: IP geolocation fallback
    if lat == 0 and lon == 0:
        ip_lat, ip_lon, ip_city = get_location_from_ip()
        if ip_lat and ip_lon:
            lat, lon = ip_lat, ip_lon
            print(f"[TOOL] 📍 Using IP location: {ip_city} ({lat}, {lon})")
    
    # Priority 4: Final fallback to Beirut
    if lat == 0 and lon == 0:
        lat, lon = 33.8938, 35.5018
        print(f"[TOOL] ⚠️ No location available, defaulting to Beirut")
    
    try:
        # Google Places API (New) - Text Search for specialty providers
        url = "https://places.googleapis.com/v1/places:searchText"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.currentOpeningHours,places.nationalPhoneNumber"
        }
        
        # Build search query
        search_text = f"{reformulated_specialty}"
        if location:
            search_text += f" in {location}"
        
        payload = {
            "textQuery": search_text,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": 10000.0  # 10km radius
                }
            },
            "maxResultCount": 5,
            "languageCode": "en"
        }
        
        print(f"[TOOL] 🔍 Google Places Text Search: '{search_text}' near ({lat}, {lon})")
        
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code != 200:
            print(f"[TOOL ERROR] Google Places API error: {response.status_code} - {response.text}")
            return f"Error searching for providers: API returned {response.status_code}"
        
        data = response.json()
        places = data.get("places", [])
        
        if not places:
            return f"No {specialty} providers found near your location. Try specifying a different area."
        
        formatted_results = []
        for i, place in enumerate(places, 1):
            name = place.get("displayName", {}).get("text", "Unknown")
            address = place.get("formattedAddress", "Address not available")
            phone = place.get("nationalPhoneNumber", "No phone listed")
            rating = place.get("rating", "N/A")
            reviews = place.get("userRatingCount", 0)
            
            # Get opening hours status
            hours = place.get("currentOpeningHours", {})
            is_open = hours.get("openNow")
            status_icon = "🟢 Open" if is_open == True else ("🔴 Closed" if is_open == False else "")
            
            # Get coordinates for navigation link
            loc = place.get("location", {})
            dest_lat = loc.get("latitude", lat)
            dest_lon = loc.get("longitude", lon)
            nav_link = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={dest_lat},{dest_lon}"
            
            # Numbered format for MapView parser compatibility
            entry = (
                f"{i}. **{name}** ({rating}⭐ from {reviews} reviews) {status_icon}\n"
                f"📍 {address}\n"
                f"📞 {phone}\n"
                f"[Navigate]({nav_link})\n"
            )
            formatted_results.append(entry)
        
        return f"Found {len(places)} {specialty} providers:\n\n" + "\n".join(formatted_results)
        
    except Exception as e:
        print(f"[TOOL ERROR] Google Places search failed: {e}")
        return f"Error searching for providers: {e}"

@tool
def book_appointment(physician_name: str, time: str, user_id: int = None) -> str:
    """
    Sends a booking request via WhatsApp using Twilio API.
    Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM in env.
    """
    print(f"[TOOL] 📅 Booking Appointment with {physician_name} at {time}")
    
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_whatsapp = os.getenv("TWILIO_WHATSAPP_FROM") 
    
    # Lookup user phone
    user_phone = None
    if user_id:
        session = SessionLocal()
        try:
            user = session.query(models.User).filter(models.User.id == user_id).first()
            if user and user.phone_number:
                user_phone = user.phone_number
        finally:
            session.close()

    if not (account_sid and auth_token and from_whatsapp):
        return f"SUCCESS (SIMULATION): Appointment request sent to {physician_name} for {time}. (Configure Twilio for real WhatsApp)."

    try:
        client = Client(account_sid, auth_token)
        
        to_whatsapp = f"whatsapp:{user_phone}" if user_phone else "whatsapp:+14155238886" # Default/Demo number
        
        msg_body = f"AEGIS BOOKING REQUEST:\nDoctor: {physician_name}\nTime: {time}\nStatus: Pending Confirmation"
        
        message = client.messages.create(
            body=msg_body,
            from_=from_whatsapp,
            to=to_whatsapp
        )
        return f"SUCCESS: Booking request sent via WhatsApp. SID: {message.sid}"
    except Exception as e:
        print(f"[TOOL ERROR] WhatsApp failed: {e}")
        return f"Failed to send WhatsApp booking: {e}"

@tool
def book_appointment_voice(
    physician_name: str, 
    physician_phone: str,
    appointment_time: str, 
    patient_name: str = "Patient",
    callback_number: str = None,
    user_id: int = None
) -> str:
    """
    Makes an AI-powered voice call to a physician's office to book an appointment.
    Uses Twilio Voice API with TTS to speak the booking request.
    The call can handle basic interactive responses using Gemini.
    """
    print(f"[TOOL] 📞 Initiating Voice Call to {physician_name} at {physician_phone}")
    
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")  # Your Twilio phone number
    
    if not all([account_sid, auth_token, twilio_phone]):
        return "SIMULATION: Voice call would be made to book appointment. Configure TWILIO_PHONE_NUMBER for real calls."
    
    # Get patient info if user_id provided
    if user_id and not callback_number:
        session = SessionLocal()
        try:
            user = session.query(models.User).filter(models.User.id == user_id).first()
            if user:
                # Use email username as patient name if no name available
                patient_name = user.email.split('@')[0] if user.email else patient_name
                callback_number = user.phone_number
        finally:
            session.close()
    
    try:
        client = Client(account_sid, auth_token)
        
        # Get the base URL for webhooks (ngrok or public URL)
        base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL", "https://your-ngrok-url.ngrok.io")
        
        # URL encode parameters
        import urllib.parse
        params = urllib.parse.urlencode({
            'physician': physician_name,
            'time': appointment_time,
            'patient': patient_name,
            'callback': callback_number or 'not provided'
        })
        
        # Create the call with TwiML webhook
        call = client.calls.create(
            to=physician_phone,
            from_=twilio_phone,
            url=f"{base_url}/twilio/voice/booking?{params}",
            timeout=30
        )
        
        return f"📞 Voice call initiated to {physician_name}!\n" \
               f"   Call SID: {call.sid}\n" \
               f"   Status: {call.status}\n" \
               f"   Requesting appointment for: {appointment_time}\n" \
               f"   Patient: {patient_name}\n" \
               f"   Callback: {callback_number or 'Not provided'}\n\n" \
               f"The AI assistant will speak with the office."
               
    except Exception as e:
        print(f"[TOOL ERROR] Voice call failed: {e}")
        return f"Failed to initiate voice call: {e}"

@tool
def read_medical_history(query: str, user_id: int = None) -> str:
    """
    Searches the patient's past medical records (Knowledge Base) for specific keywords.
    Useful for answering questions about past conditions, medications, or test results.
    IMPORTANT: Only searches the records belonging to the specified user.
    """
    # Reformulate query for better medical record matching
    search_terms = reformulate_medical_history_query(query)
    print(f"[TOOL] 📖 Reading Medical History for User {user_id}: {query}")
    print(f"[TOOL] 🔍 Search terms: {search_terms}")
    
    kb_base = "d:\\Aegis\\knowledge_base"
    
    # User-specific directory
    if user_id:
        kb_dir = os.path.join(kb_base, f"user_{user_id}")
    else:
        kb_dir = os.path.join(kb_base, "anonymous")
    
    if not os.path.exists(kb_dir):
        return "No medical history found (Knowledge Base empty)."
        
    results = []
    matched_records = []
    
    try:
        files = [f for f in os.listdir(kb_dir) if f.endswith(".md")]
        if not files:
            return "No medical records found."
            
        # Sort by newest first
        files.sort(reverse=True)
        
        for filename in files:
            filepath = os.path.join(kb_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content_lower = content.lower()
            
            # Check if any search term matches
            matches = [term for term in search_terms if term.lower() in content_lower]
            
            date_str = filename.split("_")[0]  # Timestamp
            try:
                date_readable = datetime.fromtimestamp(int(date_str)).strftime('%Y-%m-%d')
            except:
                date_readable = "Unknown Date"
            
            if matches:
                # Prioritize matched records
                matched_records.append({
                    "date": date_readable,
                    "content": content,
                    "matches": matches
                })
            else:
                # Still include recent records if no specific matches
                results.append(f"### Record from {date_readable}\n{content}\n")
                
            if len(matched_records) + len(results) >= 5:
                break
        
        # Prioritize matched records over general results
        output = []
        if matched_records:
            output.append(f"**Found {len(matched_records)} records matching: {', '.join(search_terms[:3])}**\n")
            for rec in matched_records[:3]:
                output.append(f"### Record from {rec['date']} (matched: {', '.join(rec['matches'])})\n{rec['content']}\n")
        
        # Add remaining general results if space
        remaining_slots = 5 - len(matched_records)
        if remaining_slots > 0 and results:
            output.append("\n**Other Recent Records:**\n")
            output.extend(results[:remaining_slots])
                    
        if not output:
            return "No medical records found."
            
        return "Medical History Summary:\n" + "\n".join(output)
        
    except Exception as e:
        return f"Error reading history: {e}"

@tool
def get_patient_profile(user_id: int) -> str:
    """
    Retrieves the patient's structured medical profile (Medications, Conditions, Allergies) from the database.
    Use this to get a quick overview of the patient's current health status.
    """
    print(f"[TOOL] 👤 Fetching Patient Profile for User {user_id}")
    session = SessionLocal()
    try:
        # Fetch data
        meds = session.query(models.Medication).filter(models.Medication.user_id == user_id).all()
        conditions = session.query(models.Condition).filter(models.Condition.user_id == user_id).all()
        allergies = session.query(models.Allergy).filter(models.Allergy.user_id == user_id).all()
        labs = session.query(models.LabResult).filter(models.LabResult.user_id == user_id).order_by(models.LabResult.date.desc()).limit(5).all()
        notes = session.query(models.MedicalNote).filter(models.MedicalNote.user_id == user_id).order_by(models.MedicalNote.date.desc()).limit(3).all()
        
        # Format output
        profile = f"### Patient Profile (User {user_id})\n\n"
        
        profile += "**Active Conditions:**\n"
        if conditions:
            for c in conditions:
                profile += f"- {c.name} (Status: {c.status})\n"
        else:
            profile += "- None recorded.\n"
            
        profile += "\n**Current Medications:**\n"
        if meds:
            for m in meds:
                profile += f"- {m.name} {m.dosage} ({m.frequency})\n"
        else:
            profile += "- None recorded.\n"
            
        profile += "\n**Allergies:**\n"
        if allergies:
            for a in allergies:
                profile += f"- {a.allergen} ({a.severity}): {a.reaction}\n"
        else:
            profile += "- None recorded.\n"

        profile += "\n**Recent Lab Results:**\n"
        if labs:
            for l in labs:
                profile += f"- {l.test_name}: {l.value} {l.unit} (Ref: {l.reference_range}) on {l.date}\n"
        else:
            profile += "- None recorded.\n"

        profile += "\n**Recent Medical Notes:**\n"
        if notes:
            for n in notes:
                profile += f"- {n.date} ({n.provider}): {n.summary}\n"
        else:
            profile += "- None recorded.\n"
            
        return profile
    except Exception as e:
        return f"Database error: {e}"
    finally:
        session.close()

@tool
def get_watch_vitals(user_id: int = None, hours: int = 24) -> str:
    """
    Get real-time and recent vitals from Samsung Galaxy Watch.
    Returns heart rate, SpO2, blood pressure, stress level, and trends.
    """
    print(f"[TOOL] ⌚ Fetching Galaxy Watch vitals (last {hours}h)")
    session = SessionLocal()
    
    try:
        cutoff = datetime.now() - timedelta(hours=hours)
        
        # Get recent vitals from watch
        events = session.query(models.HealthEvent).filter(
            models.HealthEvent.user_id == user_id,
            models.HealthEvent.event_type == "vitals",
            models.HealthEvent.timestamp >= cutoff
        ).order_by(models.HealthEvent.timestamp.desc()).limit(50).all()
        
        if not events:
            return "No recent watch data available. Ensure your Galaxy Watch is syncing."
        
        # Extract metrics
        heart_rates = []
        spo2_values = []
        stress_levels = []
        steps_total = 0
        latest = events[0].data if events else {}
        
        for e in events:
            if e.data.get('heart_rate'):
                heart_rates.append(e.data['heart_rate'])
            if e.data.get('spo2'):
                spo2_values.append(e.data['spo2'])
            if e.data.get('stress_level'):
                stress_levels.append(e.data['stress_level'])
            if e.data.get('steps'):
                steps_total = max(steps_total, e.data['steps'])
        
        # Build response
        result = f"### ⌚ Galaxy Watch Vitals (Last {hours}h)\n\n"
        
        # Latest reading
        result += "**Latest Reading:**\n"
        if latest.get('heart_rate'):
            result += f"- ❤️ Heart Rate: **{latest['heart_rate']} bpm**\n"
        if latest.get('spo2'):
            result += f"- 🫁 Blood Oxygen: **{latest['spo2']}%**\n"
        if latest.get('systolic_bp') and latest.get('diastolic_bp'):
            result += f"- 💓 Blood Pressure: **{latest['systolic_bp']}/{latest['diastolic_bp']} mmHg**\n"
        if latest.get('stress_level'):
            stress = latest['stress_level']
            stress_emoji = "😌" if stress < 30 else "😐" if stress < 60 else "😰"
            result += f"- {stress_emoji} Stress Level: **{stress}/100**\n"
        
        result += f"\n**{hours}-Hour Summary:**\n"
        
        if heart_rates:
            avg_hr = sum(heart_rates) / len(heart_rates)
            result += f"- Heart Rate: Avg {avg_hr:.0f} bpm (range: {min(heart_rates)}-{max(heart_rates)})\n"
        
        if spo2_values:
            avg_spo2 = sum(spo2_values) / len(spo2_values)
            result += f"- SpO2: Avg {avg_spo2:.1f}% (range: {min(spo2_values)}-{max(spo2_values)})\n"
        
        if stress_levels:
            avg_stress = sum(stress_levels) / len(stress_levels)
            result += f"- Stress: Avg {avg_stress:.0f}/100\n"
        
        if steps_total:
            result += f"- 🚶 Steps Today: **{steps_total:,}**\n"
        
        result += f"\n*{len(events)} readings from watch*"
        
        # Health insights
        alerts = []
        if heart_rates and (min(heart_rates) < 40 or max(heart_rates) > 150):
            alerts.append("⚠️ Abnormal heart rate detected in recent readings")
        if spo2_values and min(spo2_values) < 92:
            alerts.append("⚠️ Low blood oxygen detected")
        
        if alerts:
            result += "\n\n**⚠️ Alerts:**\n" + "\n".join(f"- {a}" for a in alerts)
        
        return result
        
    except Exception as e:
        return f"Error reading watch data: {e}"
    finally:
        session.close()

@tool
def get_daily_summaries(days: int = 7, user_id: int = None) -> str:
    """
    Retrieves the daily health summaries for the past N days.
    Useful for understanding recent trends in the patient's health and mood.
    """
    print(f"[TOOL] 📜 Fetching Summaries for last {days} days")
    session = SessionLocal()
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        summaries = session.query(models.DailySummary).filter(
            models.DailySummary.user_id == user_id,
            models.DailySummary.date >= start_date
        ).order_by(models.DailySummary.date.asc()).all()
        
        if not summaries:
            return "No daily summaries found for this period."
            
        result = f"### Daily Summaries (Last {days} Days)\n"
        for s in summaries:
            result += f"- **{s.date}**: {s.summary} (Mood: {s.mood})\n"
        return result
    except Exception as e:
        return f"Database error: {e}"
    finally:
        session.close()

@tool
def save_daily_summary(user_id: int = None, date_str: str = None) -> str:
    """
    Generates and saves a daily health summary for a specific date.
    Aggregates chat sessions, health events, and medical notes into a summary.
    If date_str is not provided, defaults to today.
    """
    from agents.chronicler import ChroniclerAgent
    
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    print(f"[TOOL] 📜 Generating daily summary for {date_str}")
    
    chronicler = ChroniclerAgent()
    result = chronicler.summarize_day(user_id, date_str)
    return result

@tool
def analyze_health_topic(topic: str, user_id: int = None) -> str:
    """
    Comprehensive health topic analysis combining:
    1. Daily summaries (trends and moods)
    2. Medical records from knowledge base
    3. Clinical guidance from MedlinePlus
    
    Use this for questions like "summarize my cardiac health" or "how is my diabetes management".
    """
    print(f"[TOOL] 🔬 Comprehensive analysis of: {topic}")
    
    results = []
    
    # 1. Get recent summaries related to the topic
    session = SessionLocal()
    try:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        summaries = session.query(models.DailySummary).filter(
            models.DailySummary.user_id == user_id,
            models.DailySummary.date >= start_date
        ).order_by(models.DailySummary.date.desc()).all()
        
        if summaries:
            # Filter summaries mentioning the topic
            topic_lower = topic.lower()
            relevant = [s for s in summaries if topic_lower in s.summary.lower()]
            if relevant:
                results.append("### Recent Daily Summaries\n" + "\n".join([
                    f"- **{s.date}**: {s.summary}" for s in relevant[:5]
                ]))
            else:
                results.append(f"### Daily Summaries\nNo specific mentions of '{topic}' in recent summaries.")
    finally:
        session.close()
    
    # 2. Search medical history/knowledge base
    from tools import read_medical_history
    kb_result = read_medical_history.invoke({"query": topic, "user_id": user_id})
    if kb_result and "No relevant" not in kb_result and "Error" not in kb_result:
        results.append(f"### Medical Records\n{kb_result}")
    
    # 3. Get clinical guidance from MedlinePlus
    from tools import search_clinical_guidance
    guidance = search_clinical_guidance.invoke({"query": f"{topic} management"})
    if guidance and "No clinical guidance" not in guidance and "Error" not in guidance:
        results.append(f"### Clinical Guidance\n{guidance}")
    
    if not results:
        return f"No information found about '{topic}'. Consider asking your healthcare provider."
    
    return "\n\n".join(results)

@tool
def get_health_goals(user_id: int = None) -> str:
    """
    Retrieves the patient's active health goals.
    """
    print(f"[TOOL] 🎯 Fetching Health Goals")
    session = SessionLocal()
    try:
        goals = session.query(models.HealthGoal).filter(
            models.HealthGoal.user_id == user_id,
            models.HealthGoal.status == "active"
        ).all()
        
        if not goals:
            return "No active health goals set."
            
        result = "### Active Health Goals\n"
        for g in goals:
            result += f"- {g.description}\n"
        return result
    except Exception as e:
        return f"Database error: {e}"
    finally:
        session.close()

@tool
def set_health_goal(description: str, user_id: int = None) -> str:
    """
    Sets a new health goal for the patient.
    """
    print(f"[TOOL] 🎯 Setting New Goal: {description}")
    session = SessionLocal()
    try:
        new_goal = models.HealthGoal(
            user_id=user_id,
            description=description,
            status="active"
        )
        session.add(new_goal)
        session.commit()
        return f"Successfully set new goal: {description}"
    except Exception as e:
        return f"Database error: {e}"
    finally:
        session.close()

@tool
def generate_lifestyle_plan(user_id: int) -> str:
    """
    🧬 LIFESTYLE OPTIMIZER: Multi-agent collaboration between Sentinel, MedlinePlus, and Chronicler.
    
    This tool orchestrates a comprehensive analysis to generate personalized lifestyle goals:
    1. Gathers patient profile (conditions, medications, allergies)
    2. Analyzes recent health trends from Chronicler
    3. Fetches clinical guidance from MedlinePlus for each condition
    4. Uses AI to synthesize SMART goals with clinical rationale
    5. Saves goals to database with categories and priorities
    
    Returns a comprehensive lifestyle improvement plan.
    """
    print(f"\n{'='*60}")
    print(f"[LIFESTYLE OPTIMIZER] 🧬 Starting Multi-Agent Collaboration")
    print(f"{'='*60}")
    
    from agents.llm_engine import generate_medical_response
    import json
    
    session = SessionLocal()
    results = {
        "patient_profile": None,
        "vitals_trends": None,
        "clinical_guidance": {},
        "generated_goals": [],
        "errors": []
    }
    
    try:
        # =====================================================================
        # PHASE 1: SENTINEL - Gather Patient Data
        # =====================================================================
        print("\n[PHASE 1] 📋 Sentinel: Gathering Patient Data...")
        
        # Get conditions
        conditions = session.query(models.Condition).filter(
            models.Condition.user_id == user_id,
            models.Condition.status == "Active"
        ).all()
        condition_names = [c.name for c in conditions]
        
        # Get medications
        medications = session.query(models.Medication).filter(
            models.Medication.user_id == user_id
        ).all()
        med_names = [f"{m.name} ({m.dosage})" for m in medications]
        
        # Get allergies
        allergies = session.query(models.Allergy).filter(
            models.Allergy.user_id == user_id
        ).all()
        allergy_names = [a.allergen for a in allergies]
        
        # Get existing goals
        existing_goals = session.query(models.HealthGoal).filter(
            models.HealthGoal.user_id == user_id,
            models.HealthGoal.status == "active"
        ).all()
        existing_goal_descriptions = [g.description for g in existing_goals]
        
        results["patient_profile"] = {
            "conditions": condition_names,
            "medications": med_names,
            "allergies": allergy_names,
            "existing_goals": existing_goal_descriptions
        }
        print(f"    ✓ Conditions: {condition_names}")
        print(f"    ✓ Medications: {len(med_names)} active")
        print(f"    ✓ Allergies: {allergy_names}")
        print(f"    ✓ Existing Goals: {len(existing_goal_descriptions)}")
        
        # =====================================================================
        # PHASE 2: CHRONICLER - Analyze Recent Health Trends
        # =====================================================================
        print("\n[PHASE 2] 📊 Chronicler: Analyzing Health Trends...")
        
        # Get recent vitals (last 7 days) - vitals stored in HealthEvent with event_type="vitals"
        from datetime import datetime, timedelta
        week_ago = datetime.now() - timedelta(days=7)
        
        vitals_events = session.query(models.HealthEvent).filter(
            models.HealthEvent.user_id == user_id,
            models.HealthEvent.event_type == "vitals",
            models.HealthEvent.timestamp >= week_ago
        ).order_by(models.HealthEvent.timestamp.desc()).limit(50).all()
        
        if vitals_events:
            hr_values = [v.data.get('heart_rate') for v in vitals_events if v.data.get('heart_rate')]
            spo2_values = [v.data.get('spo2') for v in vitals_events if v.data.get('spo2')]
            bp_sys_values = [v.data.get('systolic_bp') for v in vitals_events if v.data.get('systolic_bp')]
            bp_dia_values = [v.data.get('diastolic_bp') for v in vitals_events if v.data.get('diastolic_bp')]
            
            vitals_summary = {
                "heart_rate": {
                    "avg": round(sum(hr_values)/len(hr_values), 1) if hr_values else None,
                    "min": min(hr_values) if hr_values else None,
                    "max": max(hr_values) if hr_values else None
                },
                "spo2": {
                    "avg": round(sum(spo2_values)/len(spo2_values), 1) if spo2_values else None,
                    "min": min(spo2_values) if spo2_values else None
                },
                "blood_pressure": {
                    "avg_systolic": round(sum(bp_sys_values)/len(bp_sys_values), 1) if bp_sys_values else None,
                    "avg_diastolic": round(sum(bp_dia_values)/len(bp_dia_values), 1) if bp_dia_values else None
                },
                "data_points": len(vitals_events)
            }
            results["vitals_trends"] = vitals_summary
            print(f"    ✓ HR Avg: {vitals_summary['heart_rate']['avg']} bpm")
            print(f"    ✓ SpO2 Avg: {vitals_summary['spo2']['avg']}%")
            print(f"    ✓ BP Avg: {vitals_summary['blood_pressure']['avg_systolic']}/{vitals_summary['blood_pressure']['avg_diastolic']}")
        else:
            print("    ⚠ No recent vitals data")
            results["vitals_trends"] = {"note": "No recent vitals data available"}
        
        # Get recent daily summaries
        summaries = session.query(models.DailySummary).filter(
            models.DailySummary.user_id == user_id
        ).order_by(models.DailySummary.date.desc()).limit(7).all()
        
        if summaries:
            results["recent_summaries"] = [s.summary[:200] for s in summaries]
            print(f"    ✓ Found {len(summaries)} daily summaries")
        
        # =====================================================================
        # PHASE 3: MEDLINEPLUS - Fetch Clinical Guidance
        # =====================================================================
        print("\n[PHASE 3] 🏥 MedlinePlus: Fetching Clinical Guidance...")
        
        for condition in condition_names[:3]:  # Top 3 conditions
            try:
                guidance = search_clinical_guidance.invoke({"query": f"{condition} lifestyle management"})
                if guidance and "No clinical guidance found" not in guidance:
                    # Extract key points (first 600 chars)
                    results["clinical_guidance"][condition] = guidance[:600]
                    print(f"    ✓ {condition}: Guidance retrieved")
                else:
                    print(f"    ⚠ {condition}: No specific guidance found")
            except Exception as e:
                print(f"    ✗ {condition}: Error - {e}")
                results["errors"].append(f"MedlinePlus error for {condition}: {e}")
        
        # =====================================================================
        # PHASE 4: AI SYNTHESIS - Generate SMART Goals
        # =====================================================================
        print("\n[PHASE 4] 🤖 AI Synthesis: Generating Personalized Goals...")
        
        synthesis_prompt = f"""You are a clinical lifestyle advisor. Based on the following patient data, generate 3-5 personalized SMART health goals.

PATIENT PROFILE:
- Active Conditions: {', '.join(condition_names) or 'None documented'}
- Current Medications: {', '.join(med_names) or 'None'}
- Allergies: {', '.join(allergy_names) or 'None'}
- Existing Goals (avoid duplicates): {', '.join(existing_goal_descriptions) or 'None'}

RECENT VITALS TRENDS (7 days):
{json.dumps(results.get('vitals_trends', {}), indent=2)}

CLINICAL GUIDANCE FROM MEDLINEPLUS:
{json.dumps(results.get('clinical_guidance', {}), indent=2)}

Generate goals in this EXACT JSON format:
{{
    "goals": [
        {{
            "description": "Specific, measurable goal description",
            "category": "diet|exercise|medication|monitoring|lifestyle",
            "priority": "high|medium|low",
            "rationale": "Brief clinical reason for this goal",
            "condition_link": "Which condition this addresses",
            "deadline": "Suggested timeframe (e.g., '2 weeks', '1 month')"
        }}
    ],
    "summary": "Brief overall lifestyle recommendation"
}}

IMPORTANT:
- Make goals SPECIFIC and MEASURABLE (e.g., "Walk 30 minutes daily" not "Exercise more")
- Prioritize based on condition severity
- Link each goal to a specific condition when possible
- Consider medication interactions and allergies
- Don't duplicate existing goals
- Include at least one monitoring goal if patient has cardiovascular conditions
"""
        
        ai_response = generate_medical_response(synthesis_prompt, max_tokens=2000)
        
        # Parse AI response
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', ai_response)
            if json_match:
                goals_data = json.loads(json_match.group())
                generated_goals = goals_data.get("goals", [])
                summary = goals_data.get("summary", "")
                
                print(f"    ✓ Generated {len(generated_goals)} goals")
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            print(f"    ⚠ JSON parsing failed: {e}")
            # Fallback: Create basic goals based on conditions
            generated_goals = []
            for condition in condition_names[:2]:
                generated_goals.append({
                    "description": f"Monitor {condition.lower()} symptoms daily",
                    "category": "monitoring",
                    "priority": "medium",
                    "rationale": f"Regular monitoring helps manage {condition}",
                    "condition_link": condition,
                    "deadline": "Ongoing"
                })
            summary = "Basic monitoring goals created. Consult your healthcare provider for personalized advice."
        
        # =====================================================================
        # PHASE 5: SAVE GOALS TO DATABASE
        # =====================================================================
        print("\n[PHASE 5] 💾 Saving Goals to Database...")
        
        saved_count = 0
        for goal in generated_goals:
            try:
                new_goal = models.HealthGoal(
                    user_id=user_id,
                    description=goal.get("description", ""),
                    category=goal.get("category", "lifestyle"),
                    priority=goal.get("priority", "medium"),
                    rationale=goal.get("rationale", ""),
                    condition_link=goal.get("condition_link", ""),
                    deadline=goal.get("deadline", ""),
                    status="active",
                    progress=0
                )
                session.add(new_goal)
                saved_count += 1
                print(f"    ✓ Saved: {goal.get('description', '')[:50]}...")
            except Exception as e:
                print(f"    ✗ Failed to save goal: {e}")
                results["errors"].append(f"Failed to save goal: {e}")
        
        session.commit()
        print(f"\n    ✅ Total goals saved: {saved_count}")
        
        # =====================================================================
        # GENERATE FINAL REPORT
        # =====================================================================
        print(f"\n{'='*60}")
        print("[LIFESTYLE OPTIMIZER] ✅ Plan Generation Complete!")
        print(f"{'='*60}\n")
        
        report = f"""## 🧬 Personalized Lifestyle Plan

### Patient Overview
- **Conditions**: {', '.join(condition_names) or 'None documented'}
- **Current Medications**: {len(med_names)} active
- **Data Points Analyzed**: {results.get('vitals_trends', {}).get('data_points', 0)} vitals readings

### Generated Health Goals

"""
        for i, goal in enumerate(generated_goals, 1):
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(goal.get("priority", "medium"), "⚪")
            category_emoji = {
                "diet": "🥗", "exercise": "🏃", "medication": "💊",
                "monitoring": "📊", "lifestyle": "🌟"
            }.get(goal.get("category", ""), "📌")
            
            report += f"""**{i}. {goal.get('description', 'Goal')}** {priority_emoji}
   - Category: {category_emoji} {goal.get('category', 'lifestyle').title()}
   - Linked to: {goal.get('condition_link', 'General health')}
   - Timeline: {goal.get('deadline', 'Ongoing')}
   - *Rationale: {goal.get('rationale', 'Clinical best practice')}*

"""
        
        report += f"""### Summary
{summary if 'summary' in dir() else 'Goals have been created based on your health profile and clinical guidelines.'}

---
*Generated by AEGIS Lifestyle Optimizer using Sentinel analysis, Chronicler trends, and MedlinePlus clinical guidance.*
"""
        
        return report
        
    except Exception as e:
        print(f"[LIFESTYLE OPTIMIZER ERROR] {e}")
        import traceback
        traceback.print_exc()
        return f"Error generating lifestyle plan: {e}"
    finally:
        session.close()

# ==============================================================================
# EMERGENCY & ADVANCED TOOLS
# ==============================================================================

@tool
def trigger_emergency_alert(contact_number: str, message: str) -> str:
    """
    Sends an emergency SMS via Twilio if credentials exist.
    Otherwise, simulates the alert.
    Use this ONLY for CRITICAL risks.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    
    if account_sid and auth_token and from_number:
        try:
            print(f"[TOOL] 🚨 Sending REAL SMS to {contact_number}...")
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=f"AEGIS ALERT: {message}",
                from_=from_number,
                to=contact_number
            )
            return f"Alert sent successfully. SID: {message.sid}"
        except Exception as e:
            print(f"[TOOL ERROR] Twilio failed: {e}")
            return f"Failed to send SMS: {e}"
    else:
        print(f"[TOOL] 🚨 [SIMULATION] Sending SMS to {contact_number}: {message}")
        return "Alert sent successfully (SIMULATION). Configure TWILIO_ keys in .env for real SMS."

@tool
def check_critical_vitals(heart_rate: int = None, spo2: int = None, blood_pressure_systolic: int = None) -> dict:
    """
    Analyzes vital signs and determines if they are critical.
    Returns risk assessment and recommended actions.
    
    CRITICAL THRESHOLDS:
    - Heart Rate: < 40 or > 150 bpm
    - SpO2: < 90%
    - Blood Pressure (Systolic): < 90 or > 180 mmHg
    """
    print(f"[TOOL] 🚨 Checking Critical Vitals: HR={heart_rate}, SpO2={spo2}, BP={blood_pressure_systolic}")
    
    critical_conditions = []
    warnings = []
    risk_level = "normal"
    
    # Heart Rate Assessment
    if heart_rate:
        if heart_rate < 40:
            critical_conditions.append(f"CRITICAL: Severe Bradycardia (HR: {heart_rate} bpm)")
            risk_level = "critical"
        elif heart_rate > 150:
            critical_conditions.append(f"CRITICAL: Severe Tachycardia (HR: {heart_rate} bpm)")
            risk_level = "critical"
        elif heart_rate < 60:
            warnings.append(f"Warning: Bradycardia (HR: {heart_rate} bpm)")
            if risk_level != "critical":
                risk_level = "warning"
        elif heart_rate > 100:
            warnings.append(f"Warning: Tachycardia (HR: {heart_rate} bpm)")
            if risk_level != "critical":
                risk_level = "warning"
    
    # SpO2 Assessment
    if spo2:
        if spo2 < 90:
            critical_conditions.append(f"CRITICAL: Severe Hypoxemia (SpO2: {spo2}%)")
            risk_level = "critical"
        elif spo2 < 94:
            warnings.append(f"Warning: Low Oxygen Saturation (SpO2: {spo2}%)")
            if risk_level != "critical":
                risk_level = "warning"
    
    # Blood Pressure Assessment
    if blood_pressure_systolic:
        if blood_pressure_systolic < 90:
            critical_conditions.append(f"CRITICAL: Hypotension (BP: {blood_pressure_systolic} mmHg)")
            risk_level = "critical"
        elif blood_pressure_systolic > 180:
            critical_conditions.append(f"CRITICAL: Hypertensive Crisis (BP: {blood_pressure_systolic} mmHg)")
            risk_level = "critical"
        elif blood_pressure_systolic > 140:
            warnings.append(f"Warning: Elevated Blood Pressure (BP: {blood_pressure_systolic} mmHg)")
            if risk_level != "critical":
                risk_level = "warning"
    
    # Build response
    result = {
        "risk_level": risk_level,
        "critical_conditions": critical_conditions,
        "warnings": warnings,
        "recommendation": ""
    }
    
    if risk_level == "critical":
        result["recommendation"] = "IMMEDIATE MEDICAL ATTENTION REQUIRED. Consider calling emergency services."
    elif risk_level == "warning":
        result["recommendation"] = "Monitor closely. Consider contacting healthcare provider."
    else:
        result["recommendation"] = "Vitals are within normal range."
    
    return str(result)

@tool
def find_nearest_hospital(lat: float = None, lon: float = None, city: str = "Beirut") -> str:
    """
    Finds the nearest hospital using Google Places API (New).
    If lat/lon not provided, uses geocoding for the city name.
    Returns hospital name, address, rating, phone, and navigation link.
    """
    print(f"[TOOL] 🏥 Finding Nearest Hospital (City: {city})")
    
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY not found. For emergencies in Lebanon, call 140 (Red Cross) or 112 (Civil Defense)."
    
    try:
        from geopy.geocoders import Nominatim
        
        geolocator = Nominatim(user_agent="aegis_emergency_agent", timeout=5)
        
        # Get coordinates if not provided
        if not lat or not lon:
            search_query = f"{city}, Lebanon" if "lebanon" not in city.lower() else city
            location = geolocator.geocode(search_query)
            if location:
                lat, lon = location.latitude, location.longitude
            else:
                lat, lon = 33.8938, 35.5018  # Default to Beirut
        
        # Google Places API (New) - Nearby Search
        url = "https://places.googleapis.com/v1/places:searchNearby"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.currentOpeningHours,places.nationalPhoneNumber"
        }
        
        payload = {
            "includedTypes": ["hospital"],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": 10000.0  # 10km for emergencies
                }
            }
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        
        if "error" in data:
            error_msg = data["error"].get("message", "API error")
            return f"Hospital search failed: {error_msg}. For emergencies, call 140 (Red Cross)."
        
        results = data.get("places", [])
        
        if not results:
            return "No hospitals found within 10km. For emergencies in Lebanon, call 140 (Red Cross) or 112."
        
        formatted = ["🏥 **Nearest Hospitals:**\n"]
        for i, place in enumerate(results, 1):
            name = place.get("displayName", {}).get("text", "Unknown")
            address = place.get("formattedAddress", "No address")
            rating = place.get("rating", "N/A")
            phone = place.get("nationalPhoneNumber", "")
            is_open = place.get("currentOpeningHours", {}).get("openNow")
            open_status = "🟢 Open" if is_open else ("🔴 Closed" if is_open is False else "")
            
            location = place.get("location", {})
            h_lat = location.get("latitude", lat)
            h_lon = location.get("longitude", lon)
            
            nav_link = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={h_lat},{h_lon}&travelmode=driving"
            
            entry = f"**{i}. {name}** ({rating}⭐) {open_status}\n   📍 {address}"
            if phone:
                entry += f"\n   📞 {phone}"
            entry += f"\n   🧭 [Navigate to Hospital]({nav_link})"
            
            formatted.append(entry)
        
        formatted.append("\n⚠️ **Emergency Numbers:** 140 (Red Cross) | 112 (Civil Defense)")
        return "\n\n".join(formatted)
        
    except Exception as e:
        print(f"[TOOL ERROR] Hospital search failed: {e}")
        return f"Error finding hospitals: {e}. For emergencies in Lebanon, call 140 (Red Cross) or 112 (Civil Defense)."

@tool
def dispatch_emergency_services(
    patient_name: str,
    condition: str,
    location: str,
    phone_number: str = None,
    user_id: int = None
) -> str:
    """
    Dispatches emergency services (ambulance) for critical situations.
    This tool will:
    1. Send SMS alert to emergency contact
    2. Log the emergency in the database
    3. Attempt to contact emergency services (simulated in demo)
    
    USE ONLY FOR GENUINE EMERGENCIES.
    """
    print(f"[TOOL] 🚑 DISPATCHING EMERGENCY SERVICES for {patient_name}")
    print(f"       Condition: {condition}")
    print(f"       Location: {location}")
    
    results = []
    
    # 1. Get user's emergency contact from database
    session = SessionLocal()
    emergency_contact = None
    try:
        if user_id:
            user = session.query(models.User).filter(models.User.id == user_id).first()
            if user:
                emergency_contact = user.phone_number  # Could also have a separate emergency_contact field
    finally:
        session.close()
    
    # 2. Send emergency SMS via Twilio
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    
    emergency_message = f"""🚨 AEGIS EMERGENCY ALERT 🚨
Patient: {patient_name}
Condition: {condition}
Location: {location}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This is an automated emergency alert from the AEGIS Health System.
Please respond immediately or call emergency services (140 - Red Cross, 112 - Civil Defense)."""

    if account_sid and auth_token and from_number:
        try:
            client = Client(account_sid, auth_token)
            
            # Send to emergency contact
            target_number = phone_number or emergency_contact or os.getenv("DEFAULT_EMERGENCY_NUMBER")
            
            if target_number:
                message = client.messages.create(
                    body=emergency_message,
                    from_=from_number,
                    to=target_number
                )
                results.append(f"✅ Emergency SMS sent to {target_number}. SID: {message.sid}")
            else:
                results.append("⚠️ No emergency contact number available for SMS.")
                
        except Exception as e:
            results.append(f"❌ SMS failed: {e}")
    else:
        results.append("📱 SMS SIMULATION: " + emergency_message[:100] + "...")
    
    # 3. Log emergency in database (if models support it)
    try:
        session = SessionLocal()
        # You could add an EmergencyLog model to track these
        # For now, we'll just log to console
        print(f"[EMERGENCY LOG] {datetime.now()}: {patient_name} - {condition} at {location}")
        session.close()
        results.append("📋 Emergency logged to system.")
    except Exception as e:
        results.append(f"⚠️ Could not log emergency: {e}")
    
    # 4. Provide emergency numbers
    emergency_numbers = """
📞 **Emergency Services (Lebanon):**
- Red Cross Ambulance: 140
- Civil Defense: 125
- Internal Security: 112
- Fire Department: 175

🌍 **International:**
- WHO Emergency: Check local listings
"""
    
    results.append(emergency_numbers)
    
    return "\n\n".join(results)


@tool
def assess_and_respond_emergency(
    heart_rate: int = None,
    spo2: int = None,
    blood_pressure_systolic: int = None,
    patient_location: str = "Unknown",
    user_id: int = None
) -> str:
    """
    COMPREHENSIVE EMERGENCY TOOL: Assesses vitals and automatically responds to emergencies.
    
    This tool:
    1. Checks if vitals are critical
    2. Finds nearest hospitals
    3. Dispatches emergency services if critical
    
    Use this when monitoring detects abnormal vitals or patient reports emergency symptoms.
    """
    print(f"[TOOL] 🆘 EMERGENCY ASSESSMENT STARTED")
    
    response_parts = []
    
    # 1. Check vital signs
    critical_conditions = []
    risk_level = "normal"
    
    if heart_rate:
        if heart_rate < 40 or heart_rate > 150:
            critical_conditions.append(f"Heart Rate: {heart_rate} bpm (CRITICAL)")
            risk_level = "critical"
        elif heart_rate < 60 or heart_rate > 100:
            critical_conditions.append(f"Heart Rate: {heart_rate} bpm (Warning)")
            if risk_level != "critical":
                risk_level = "warning"
    
    if spo2:
        if spo2 < 90:
            critical_conditions.append(f"SpO2: {spo2}% (CRITICAL - Hypoxemia)")
            risk_level = "critical"
        elif spo2 < 94:
            critical_conditions.append(f"SpO2: {spo2}% (Warning)")
            if risk_level != "critical":
                risk_level = "warning"
    
    if blood_pressure_systolic:
        if blood_pressure_systolic < 90 or blood_pressure_systolic > 180:
            critical_conditions.append(f"Blood Pressure: {blood_pressure_systolic} mmHg (CRITICAL)")
            risk_level = "critical"
    
    # 2. Build assessment
    if risk_level == "critical":
        response_parts.append("🚨 **CRITICAL EMERGENCY DETECTED**\n")
        response_parts.append("**Abnormal Vitals:**")
        for cond in critical_conditions:
            response_parts.append(f"  • {cond}")
        
        # Find hospitals
        response_parts.append("\n**Locating nearest hospitals...**")
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="aegis_emergency")
            location = geolocator.geocode(patient_location)
            if location:
                # Just include the location info
                response_parts.append(f"📍 Patient Location: {patient_location} ({location.latitude:.4f}, {location.longitude:.4f})")
        except:
            response_parts.append(f"📍 Patient Location: {patient_location}")
        
        # Emergency services info
        response_parts.append("\n**🚑 IMMEDIATE ACTION REQUIRED:**")
        response_parts.append("1. Call 140 (Red Cross) or 112 (Civil Defense) immediately")
        response_parts.append("2. Do not move the patient unless in danger")
        response_parts.append("3. Keep the patient calm and monitor breathing")
        response_parts.append("4. If patient is unconscious, check for pulse and breathing")
        response_parts.append("5. Be ready to perform CPR if trained")
        
        response_parts.append("\n⚠️ **Alert has been logged. Emergency contacts notified (if configured).**")
        
    elif risk_level == "warning":
        response_parts.append("⚠️ **HEALTH WARNING**\n")
        response_parts.append("**Abnormal Vitals Detected:**")
        for cond in critical_conditions:
            response_parts.append(f"  • {cond}")
        response_parts.append("\n**Recommendation:** Monitor closely and contact your healthcare provider if symptoms persist or worsen.")
        
    else:
        response_parts.append("✅ **Vitals Assessment: Normal**")
        response_parts.append("All monitored vital signs are within acceptable ranges.")
        response_parts.append("Continue routine monitoring and maintain healthy habits.")
    
    return "\n".join(response_parts)

@tool
def simulate_ecg(duration: int = 10, heart_rate: int = 70) -> str:
    """
    Generates a simulated ECG signal using NeuroKit2.
    Useful for testing signal analysis pipelines without real sensors.
    """
    print(f"[TOOL] 💓 Simulating ECG: {duration}s at {heart_rate} bpm")
    try:
        import neurokit2 as nk
        import numpy as np
        
        # Simulate ECG
        ecg_signal = nk.ecg_simulate(duration=duration, sampling_rate=100, heart_rate=heart_rate)
        
        # Analyze it immediately (using Chronicler logic)
        from agents.chronicler import ChroniclerAgent
        chronicler = ChroniclerAgent()
        analysis = chronicler.analyze_signal(ecg_signal.tolist(), sampling_rate=100)
        
        return f"Simulated ECG Analysis:\n{analysis}"
    except ImportError:
        return "NeuroKit2 not installed."
    except Exception as e:
        return f"Simulation failed: {e}"

@tool
def award_habitica_xp(task_name: str) -> str:
    """
    Awards XP to the user's gamified avatar for completing a health task.
    """
    from agents.strategist import StrategistAgent
    strategist = StrategistAgent()
    return strategist.award_habitica_xp(task_name)

@tool
def get_monday_briefing(user_id: int = None) -> str:
    """
    Retrieves the weekly 'Monday Morning Briefing' from the Chronicler.
    """
    from agents.chronicler import ChroniclerAgent
    chronicler = ChroniclerAgent()
    return chronicler.generate_monday_briefing(user_id)

@tool
def check_med_safety(med_name: str, symptom: str) -> str:
    """
    Checks if a symptom is a known side effect of a medication using OpenFDA.
    """
    from agents.strategist import StrategistAgent
    strategist = StrategistAgent()
    return strategist.check_medication_safety(med_name, symptom)


# ==============================================================================
# EMERGENCY CALL TOOL
# ==============================================================================

@tool
def emergency_call(user_id: int, reason: str) -> str:
    """
    🚨 CRITICAL: Initiates an emergency phone call to the user's designated emergency contacts.
    
    USE THIS TOOL WHEN:
    1. User explicitly asks to call emergency contacts or for emergency help
    2. User describes symptoms of heart attack, stroke, severe breathing difficulty
    3. User expresses suicidal thoughts or self-harm intentions
    4. User reports loss of consciousness, severe bleeding, or other life-threatening conditions
    5. Vital signs reach critical thresholds (auto-triggered)
    
    Args:
        user_id: The patient's user ID (from session context)
        reason: Clear description of why emergency call is being made
    
    Returns:
        Status of the emergency call attempt
    
    IMPORTANT: This tool actually makes real phone calls. Use with appropriate urgency.
    """
    print(f"\n🚨🚨🚨 [EMERGENCY CALL TOOL] Activated for user {user_id}")
    print(f"    Reason: {reason}")
    
    try:
        from integrations.twilio_emergency import make_emergency_call, is_twilio_configured
        
        if not is_twilio_configured():
            return (
                "⚠️ EMERGENCY SYSTEM NOT CONFIGURED\n\n"
                "The emergency call system is not set up. To enable:\n"
                "1. Create a Twilio account at twilio.com\n"
                "2. Set environment variables: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER\n\n"
                "For immediate emergency, please call your local emergency services (911 in US)."
            )
        
        # Get latest vitals for context
        session = SessionLocal()
        try:
            latest_vitals = session.query(models.HealthEvent).filter(
                models.HealthEvent.user_id == user_id,
                models.HealthEvent.event_type == "vitals"
            ).order_by(models.HealthEvent.timestamp.desc()).first()
            
            vitals_data = latest_vitals.data if latest_vitals else None
        finally:
            session.close()
        
        # Make the call
        result = make_emergency_call(
            user_id=user_id,
            reason=reason,
            trigger_type="agent_detected",
            vitals=vitals_data
        )
        
        if result.get("success"):
            calls = result.get("calls", [])
            call_summary = "\n".join([
                f"  • {c['contact_name']}: Call initiated (ID: {c.get('call_sid', 'N/A')[:10]}...)"
                for c in calls if not c.get("error")
            ])
            
            return (
                f"🚨 EMERGENCY CALLS INITIATED\n\n"
                f"Reason: {reason}\n"
                f"Patient: {result.get('patient')}\n\n"
                f"Contacts being called:\n{call_summary}\n\n"
                f"Calls are in progress. Emergency contacts will receive voice messages "
                f"with patient status and instructions to check on you immediately.\n\n"
                f"If this is a life-threatening emergency, also call 911 directly."
            )
        else:
            error = result.get("error", "Unknown error")
            action = result.get("action_required", "")
            
            return (
                f"⚠️ EMERGENCY CALL COULD NOT BE COMPLETED\n\n"
                f"Error: {error}\n"
                f"{action}\n\n"
                f"For immediate emergency, please call 911 directly."
            )
            
    except Exception as e:
        print(f"[EMERGENCY CALL ERROR] {e}")
        return (
            f"❌ EMERGENCY SYSTEM ERROR\n\n"
            f"Technical error: {str(e)}\n\n"
            f"For immediate emergency, please call 911 directly."
        )


@tool 
def get_emergency_contacts(user_id: int) -> str:
    """
    Retrieves the user's configured emergency contacts.
    Use this to verify emergency contacts exist before making calls.
    """
    try:
        from integrations.twilio_emergency import get_emergency_contacts as get_contacts
        
        contacts = get_contacts(user_id)
        
        if not contacts:
            return (
                "No emergency contacts configured.\n"
                "Please add emergency contacts in Settings → Emergency Contacts."
            )
        
        contact_list = "\n".join([
            f"  {i+1}. {c.name} ({c.relationship}) - {c.phone_number}"
            for i, c in enumerate(contacts)
        ])
        
        return f"Emergency Contacts:\n{contact_list}"
        
    except Exception as e:
        return f"Error retrieving contacts: {e}"


@tool
def check_vitals_critical(user_id: int) -> str:
    """
    Checks if the user's current vital signs are at critical levels.
    Returns critical alerts if any thresholds are exceeded.
    Use this to assess whether emergency intervention is needed.
    """
    try:
        from integrations.twilio_emergency import check_critical_vitals, CRITICAL_THRESHOLDS
        
        session = SessionLocal()
        try:
            # Get latest vitals
            latest = session.query(models.HealthEvent).filter(
                models.HealthEvent.user_id == user_id,
                models.HealthEvent.event_type == "vitals"
            ).order_by(models.HealthEvent.timestamp.desc()).first()
            
            if not latest:
                return "No recent vital signs data available."
            
            vitals = latest.data
            critical = check_critical_vitals(vitals)
            
            if critical:
                alerts = "\n".join([f"  🚨 {a['message']}" for a in critical])
                return (
                    f"⚠️ CRITICAL VITAL SIGNS DETECTED:\n{alerts}\n\n"
                    f"Recommend immediate medical attention."
                )
            else:
                return (
                    f"Vital signs within normal ranges:\n"
                    f"  • Heart Rate: {vitals.get('heart_rate', 'N/A')} bpm\n"
                    f"  • SpO2: {vitals.get('spo2', 'N/A')}%\n"
                    f"  • BP: {vitals.get('systolic_bp', 'N/A')}/{vitals.get('diastolic_bp', 'N/A')} mmHg"
                )
        finally:
            session.close()
            
    except Exception as e:
        return f"Error checking vitals: {e}"


# ============================================================================
# WhatsApp Booking Tool
# ============================================================================

@tool
def book_appointment_whatsapp(
    physician_name: str,
    physician_phone: str,
    preferred_time: str,
    reason: str,
    user_id: int
) -> str:
    """
    Book an appointment with a physician via WhatsApp conversation.
    Sends a booking request to the physician's office and manages the conversation.
    
    Use this when the user wants to book an appointment and you have:
    - Physician name and phone number
    - Preferred appointment time
    - Reason for visit
    
    The system will send a WhatsApp message and notify the user when the office responds.
    
    Args:
        physician_name: Name of the physician/doctor
        physician_phone: Physician's phone number (WhatsApp enabled)
        preferred_time: Preferred date/time (e.g., "Monday at 3pm", "December 5th morning")
        reason: Reason for the appointment
        user_id: The user's ID
        
    Returns:
        Status message about the booking request
    """
    try:
        from integrations.twilio_whatsapp import book_via_whatsapp, is_whatsapp_configured
        
        if not is_whatsapp_configured():
            return (
                "WhatsApp booking is not configured. "
                "Would you like me to try booking via voice call instead?"
            )
        
        result = book_via_whatsapp(
            user_id=user_id,
            physician_name=physician_name,
            physician_phone=physician_phone,
            preferred_time=preferred_time,
            reason=reason
        )
        
        return result
        
    except Exception as e:
        return f"Error initiating WhatsApp booking: {e}"


@tool
def check_whatsapp_booking_status(session_id: str) -> str:
    """
    Check the status of a WhatsApp booking request.
    
    Args:
        session_id: The booking session ID returned when initiating the booking
        
    Returns:
        Current status of the booking conversation
    """
    try:
        from integrations.twilio_whatsapp import get_booking_status
        return get_booking_status(session_id)
    except Exception as e:
        return f"Error checking booking status: {e}"
