from typing import TypedDict, List, Annotated, Union
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from agents.llm_engine import generate_medical_response
import os

# ============================================================================
# SLIDING WINDOW CONFIGURATION
# ============================================================================
# Dynamic sliding window for conversation history to prevent context overflow
# and improve response quality by focusing on recent, relevant context.

# Maximum number of messages to keep in the active window
MAX_WINDOW_SIZE = int(os.getenv("AEGIS_MAX_WINDOW_SIZE", "20"))

# Number of recent messages to always preserve (not summarized)
PRESERVE_RECENT = int(os.getenv("AEGIS_PRESERVE_RECENT", "6"))

# Whether to summarize old messages (vs just dropping them)
SUMMARIZE_OLD = os.getenv("AEGIS_SUMMARIZE_OLD", "false").lower() == "true"


def sliding_window_messages(existing: list, new: list) -> list:
    """
    Custom message reducer that implements a sliding window.
    
    Strategy:
    1. Always keep the first system message (patient context)
    2. Always keep the most recent PRESERVE_RECENT messages
    3. When over MAX_WINDOW_SIZE, either:
       - Summarize older messages into a single system message
       - Or drop older messages (keeping important tool results)
    """
    # Use default add_messages to combine
    combined = add_messages(existing, new)
    
    # If under limit, return as-is
    if len(combined) <= MAX_WINDOW_SIZE:
        return combined
    
    print(f"[SLIDING WINDOW] Trimming history: {len(combined)} -> {MAX_WINDOW_SIZE} messages")
    
    # Separate messages by type
    system_messages = []
    conversation_messages = []
    
    for msg in combined:
        if isinstance(msg, SystemMessage):
            # Keep important system messages (patient context, critical tool results)
            content = msg.content.lower()
            if any(keyword in content for keyword in [
                "patient context", "medical record", "emergency", "critical", 
                "vital", "alert", "diagnosis", "medication"
            ]):
                system_messages.append(msg)
        else:
            conversation_messages.append(msg)
    
    # Calculate how many conversation messages we can keep
    available_slots = MAX_WINDOW_SIZE - len(system_messages) - 1  # -1 for summary
    
    if available_slots < PRESERVE_RECENT:
        available_slots = PRESERVE_RECENT
    
    # Keep the most recent conversation messages
    recent_messages = conversation_messages[-available_slots:] if conversation_messages else []
    
    # Create a summary of what was dropped (if enabled and there were dropped messages)
    dropped_count = len(conversation_messages) - len(recent_messages)
    
    result = []
    
    # Add important system messages first
    result.extend(system_messages[:3])  # Max 3 system context messages
    
    # Add summary of dropped history if any
    if dropped_count > 0:
        summary_msg = SystemMessage(content=f"[Prior conversation: {dropped_count} earlier messages summarized. Recent context preserved.]")
        result.append(summary_msg)
    
    # Add recent conversation messages
    result.extend(recent_messages)
    
    print(f"[SLIDING WINDOW] Final history: {len(result)} messages (dropped {dropped_count})")
    
    return result
from tools import (
    search_medical_knowledge,
    search_clinical_guidance,  
    locate_nearest_facility, 
    trigger_emergency_alert, 
    search_physician, 
    search_my_physicians, 
    read_medical_history, 
    get_patient_profile,
    find_providers_online,
    book_appointment,
    book_appointment_voice,
    save_physician_contact,
    add_calendar_event,
    get_daily_summaries,
    get_health_goals,
    set_health_goal,
    # Emergency Response Tools
    check_critical_vitals,
    find_nearest_hospital,
    dispatch_emergency_services,
    assess_and_respond_emergency,
    # Emergency Call Tools (Twilio)
    emergency_call,
    get_emergency_contacts,
    # Advanced Tools
    simulate_ecg,
    award_habitica_xp,
    get_monday_briefing,
    check_med_safety,
    # Lifestyle Optimizer
    generate_lifestyle_plan
)
import re

# Tool Registry
from tools import save_daily_summary, analyze_health_topic, get_watch_vitals

TOOLS = {
    "GUIDANCE": search_clinical_guidance,  # MedlinePlus - PRIMARY for patient advice
    "SEARCH": search_clinical_guidance,  # Default search now uses MedlinePlus
    "SEARCH_PUBMED": search_medical_knowledge,  # Keep PubMed for research queries
    "LOCATE_FACILITY": locate_nearest_facility,
    "LOCATE": locate_nearest_facility,  # Alias for prompt
    "ALERT": trigger_emergency_alert,
    "SEARCH_PHYSICIAN": search_physician,
    "MY_PHYSICIAN": search_my_physicians,  # Personal contacts lookup
    "READ_HISTORY": read_medical_history,
    "GET_PROFILE": get_patient_profile,
    "FIND_PROVIDERS": find_providers_online,
    "BOOK_APPOINTMENT": book_appointment,
    "CALL_PHYSICIAN": book_appointment_voice,  # AI voice call booking
    "SAVE_PHYSICIAN": save_physician_contact,
    "ADD_CALENDAR": add_calendar_event,
    "GET_SUMMARIES": get_daily_summaries,
    "SAVE_SUMMARY": save_daily_summary,  # Generate and save daily summary
    "ANALYZE_HEALTH": analyze_health_topic,  # Comprehensive topic analysis
    "WATCH_VITALS": get_watch_vitals,  # Galaxy Watch real-time vitals
    "GET_GOALS": get_health_goals,
    "SET_GOAL": set_health_goal,
    # Emergency Tools
    "CHECK_VITALS": check_critical_vitals,
    "FIND_HOSPITAL": find_nearest_hospital,
    "DISPATCH_EMERGENCY": dispatch_emergency_services,
    "EMERGENCY_RESPONSE": assess_and_respond_emergency,
    # Emergency Call (Twilio)
    "EMERGENCY_CALL": emergency_call,
    "CALL_EMERGENCY": emergency_call,  # Alias
    "GET_EMERGENCY_CONTACTS": get_emergency_contacts,
    # Advanced Tools
    "SIMULATE_ECG": simulate_ecg,
    "AWARD_XP": award_habitica_xp,
    "GET_BRIEFING": get_monday_briefing,
    "CHECK_SAFETY": check_med_safety,
    # Lifestyle Optimizer - Multi-Agent Collaboration
    "LIFESTYLE_PLAN": generate_lifestyle_plan,
    "OPTIMIZE_LIFESTYLE": generate_lifestyle_plan  # Alias
}

class AgentState(TypedDict):
    messages: Annotated[list, sliding_window_messages]  # Dynamic sliding window for history management
    medical_record: str
    user_context: str
    iterations: int
    user_id: int
    user_location: dict  # {lat: float, lon: float} from browser geolocation

def reasoning_node(state: AgentState):
    messages = state['messages']
    medical_record = state['medical_record']
    user_context = state['user_context']
    iterations = state.get('iterations', 0)
    
    # Debug: show all messages in state
    print(f"[GRAPH DEBUG] Messages in state ({len(messages)}):")
    for i, msg in enumerate(messages):
        print(f"  [{i}] {type(msg).__name__}: {msg.content[:100]}...")
    
    # Construct Prompt
    # We rebuild the prompt each time to include the conversation history
    # This is a "Chat" simulation for a completion-based LLM
    
    history_text = ""
    has_tool_result = False
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history_text += f"User: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            history_text += f"Sentinel: {msg.content}\n"
        elif isinstance(msg, SystemMessage):
            # Make tool results very prominent
            if "Tool Result" in msg.content:
                history_text += f"\n>>> TOOL OUTPUT <<<\n{msg.content}\n>>> END TOOL OUTPUT <<<\n\n"
                has_tool_result = True
            else:
                history_text += f"System: {msg.content}\n"
            
    prompt = f"""<system>
    You are Sentinel, an advanced AI medical assistant.
    
    GOAL: Analyze the patient's medical record and context to provide safe, actionable advice.
    
    PATIENT CONTEXT:
    {user_context}
    
    MEDICAL RECORD:
    {medical_record}
    
    AVAILABLE TOOLS:
    - [GET_PROFILE: user_id] -> Get structured list of active conditions, medications, and allergies. USE THIS for general health context.
    - [SEARCH: query] -> Search MedlinePlus for patient-friendly clinical guidance. USE THIS for condition management, treatment info, lifestyle advice.
    - [GUIDANCE: query] -> Same as SEARCH - patient-friendly guidance from MedlinePlus (NIH).
    - [SEARCH_PUBMED: query] -> Search PubMed for academic research papers. ONLY use when user asks for "studies", "research", or "latest evidence".
    - [READ_HISTORY: query] -> Search patient's PAST medical records for specific keywords (e.g., "diabetes", "medication").
    - [MY_PHYSICIAN: name] -> Search patient's PERSONAL address book for a doctor. USE THIS FIRST for doctor lookups.
    - [SEARCH_PHYSICIAN: name, clinic] -> Search for a referring physician mentioned in the record (NOT the patient).
    - [FIND_PROVIDERS: specialty, location] -> Search Google Maps for doctors/specialists. USE THIS when user asks to "find a doctor" or "need a specialist".
    - [BOOK_APPOINTMENT: physician_name, time] -> Book an appointment via WhatsApp message.
    - [CALL_PHYSICIAN: physician_name, phone, time] -> Make an AI voice call to book appointment. Use when user explicitly wants to call.
    - [ADD_CALENDAR: summary, start_time, end_time] -> Add event to Google Calendar. Dates in ISO format (YYYY-MM-DDTHH:MM:SS).
    - [SAVE_PHYSICIAN: name, specialty, clinic, phone] -> Save a new physician to contacts.
    - [GET_SUMMARIES: days] -> Get daily health summaries (default 7 days). Use to understand recent trends.
    - [SAVE_SUMMARY: date] -> Generate and save today's daily summary. Use when user asks to "save summary" or "update my daily log".
    - [ANALYZE_HEALTH: topic] -> COMPREHENSIVE health topic analysis. Combines summaries + medical records + MedlinePlus guidance.
      USE THIS when user asks: "summarize my cardiac health", "how is my diabetes?", "give me a health summary", "analyze my blood pressure".
    - [WATCH_VITALS: hours] -> Get real-time vitals from Samsung Galaxy Watch (heart rate, SpO2, BP, stress, steps).
      USE THIS when user asks: "what's my heart rate?", "check my watch", "how are my vitals?", "show my Galaxy Watch data".
    - [GET_GOALS: user_id] -> Get active health goals.
    - [SET_GOAL: description] -> Set a new health goal.
    - [LOCATE: facility_type, city] -> Find nearest hospital/pharmacy/clinic in a city (e.g., "pharmacy, Hamra").
    - [ALERT: message] -> Trigger emergency SMS (CRITICAL ONLY).
    
    EMERGENCY TOOLS (Use when patient reports critical symptoms or vitals):
    - [CHECK_VITALS: heart_rate, spo2, blood_pressure] -> Assess if vital signs are critical (e.g., HR<40, SpO2<90).
    - [FIND_HOSPITAL: city] -> Find nearest hospitals with distance, phone, and address.
    - [DISPATCH_EMERGENCY: patient_name, condition, location] -> Send emergency alerts and provide emergency numbers.
    - [EMERGENCY_RESPONSE: heart_rate, spo2, blood_pressure, location] -> Full emergency assessment with hospital lookup.
    
    🚨 EMERGENCY CALL TOOL (CRITICAL - Twilio Integration):
    - [EMERGENCY_CALL: user_id, reason] -> MAKE A REAL PHONE CALL to patient's emergency contacts.
      USE THIS IMMEDIATELY WHEN:
      • User says: "call my emergency contact", "call for help", "I need an ambulance", "call my family"
      • User describes: heart attack symptoms (chest pain, arm pain), stroke symptoms (face drooping, slurred speech)
      • User reports: severe breathing difficulty, loss of consciousness, suicidal thoughts
      • Vital signs are critical: HR<40 or HR>150, SpO2<88, BP>180/120
      The system will call up to 3 emergency contacts with voice message about the emergency.
    - [GET_EMERGENCY_CONTACTS: user_id] -> View configured emergency contacts before calling.
    
    ADVANCED TOOLS:
    - [SIMULATE_ECG: duration, heart_rate] -> Generate and analyze a fake ECG signal (e.g., "Simulate ECG for 10s at 80bpm").
    - [AWARD_XP: task_name] -> Give the user XP in Habitica for completing a task (e.g., "Took meds").
    - [GET_BRIEFING: user_id] -> Get the "Monday Morning Briefing" (weekly summary).
    - [CHECK_SAFETY: med_name, symptom] -> Check if a symptom is a side effect of a med (OpenFDA).
    
    LIFESTYLE OPTIMIZER (Multi-Agent Collaboration):
    - [LIFESTYLE_PLAN: user_id] -> 🧬 COMPREHENSIVE lifestyle planning that:
      1. Gathers patient profile from Sentinel (conditions, meds, allergies)
      2. Analyzes health trends from Chronicler (vitals, summaries)
      3. Fetches clinical guidance from MedlinePlus
      4. Generates personalized SMART goals with clinical rationale
      5. Saves goals to database with categories and priorities
      USE THIS when patient asks: "Help me improve my lifestyle", "Create a health plan", "What goals should I set?", "How can I manage my conditions better?"
    
    HISTORY:
    {history_text}
    
    INSTRUCTIONS:
    1. For simple greetings ONLY (like "Hi", "Hello"): Answer with a greeting.
    
    2. CRITICAL - TOOL OUTPUT HANDLING:
       If the history contains ">>> TOOL OUTPUT <<<", you MUST:
       - Read the data carefully
       - For LOCATION/MAP RESULTS (LOCATE, FIND_HOSPITAL, FIND_PROVIDERS): OUTPUT THE FULL RESULT VERBATIM!
         Include ALL the formatted entries with addresses, phone numbers, ratings, and [Navigate](url) links exactly as shown.
         Example: "Found 5 nearby hospitals:\n\n1. **AUBMC** (4.5⭐)\n   📍 Address\n   📞 Phone\n   🧭 [Navigate](https://...)"
       - For other tools: Summarize or explain the data to answer the user's question
       - DO NOT say generic responses like "Hello! How can I help you?"
       - DO NOT ask if they want you to use a tool - the tool was already used!
       
    3. AUTOMATIC TOOL USAGE - DO NOT ASK FOR PERMISSION:
       When the user asks about health data, records, or needs information - USE THE TOOL IMMEDIATELY.
       Do NOT say "Would you like me to...", "I can use...", or "I will..." - just output the tool command.
       NEVER say you will do something without actually outputting the tool command in the SAME response.
       - "How are my records?" / "Am I in good shape?" → Multi-step analysis:
         Step 1: [GET_PROFILE: user_id] to get conditions, meds, allergies
         Step 2: [READ_HISTORY: health] to get detailed records  
         Step 3: After receiving data, get clinical guidance with [SEARCH: <condition> management]
         Step 4: Synthesize a comprehensive health analysis for the patient
       - "Do you have my records?" / "What's in my history?" → [READ_HISTORY: medical records]
       - "What causes diabetes?" / "How do I manage hypertension?" → [SEARCH: diabetes management] (MedlinePlus for patient-friendly guidance)
       - "What are the latest studies on heart failure?" → [SEARCH_PUBMED: heart failure treatment] (Only for research queries!)
       - "Find Dr. Smith in my contacts" → [MY_PHYSICIAN: Smith]
       - "I need a kidney doctor" / "Find me an eye doctor" / "Ophthalmologist near me" → [FIND_PROVIDERS: Ophthalmologist, Beirut]
       - IMPORTANT: For finding doctors/specialists, use FIND_PROVIDERS (Google Maps), NOT SEARCH!
       - "Book with Dr. X at 10am" → [BOOK_APPOINTMENT: Dr. X, 10am]
       - "Call Dr. X at +123456 to book Friday 5pm" → [CALL_PHYSICIAN: Dr. X, +123456, Friday 5pm]
       - IMPORTANT: When user provides a phone number and wants to CALL, use CALL_PHYSICIAN (voice call), NOT BOOK_APPOINTMENT!
    4. When using a tool: Output ONLY the tool command on that turn, e.g., [READ_HISTORY: medical records]. Nothing else.
    5. After receiving tool results: Provide a helpful response based on the data. NEVER say "the search results show" or "according to the tool" - speak as if you already knew this information.
    6. NEVER include tool suggestions in your answer - either use the tool OR answer directly. NEVER expose that you used a tool.
    7. IMPORTANT: Do NOT search for the PATIENT's name as a physician. Only search for REFERRING PHYSICIANS mentioned in the record.
    8. STANDALONE RESPONSES: Each response must be complete and standalone. Do NOT repeat, summarize, or reference your previous responses. Answer the CURRENT question directly without preamble about what you said before.
    
    Output your response now. Provide a FRESH, standalone answer to the user's most recent message.
    </system>
    Sentinel:"""
    
    print(f"[GRAPH] Reasoning Node (Iter {iterations})...")
    
    # Debug: Show if tool output is present
    if has_tool_result:
        print(f"[GRAPH] Tool output detected in history!")
        print(f"[GRAPH] History preview: {history_text[-500:]}")  # Last 500 chars
    
    # Use higher max_tokens when tool output contains location data (long formatted results)
    output_tokens = 1500 if has_tool_result else 512
    response_text = generate_medical_response(prompt, max_tokens=output_tokens)
    
    return {
        "messages": [AIMessage(content=response_text)],
        "iterations": iterations + 1
    }

def tool_execution_node(state: AgentState):
    """
    The Hand: Executes tools requested by the Brain.
    """
    messages = state['messages']
    last_message = messages[-1]
    content = last_message.content
    
    print(f"[GRAPH] Tool Execution Node: Checking '{content}'")
    
    new_messages = []
    
    # Regex to find tool calls like [TOOL: args]
    # Supports multiple tools in one turn
    tool_calls = re.findall(r"\[([A-Z_]+):(.*?)\]", content)
    
    # Also handle ```tool_code format that Gemini sometimes uses
    if not tool_calls:
        # Try alternate format: ```tool_code\nTOOL: args\n```
        alt_match = re.search(r"```(?:tool_code)?\s*\n?\s*([A-Z_]+):\s*(.+?)\s*```", content, re.DOTALL)
        if alt_match:
            tool_calls = [(alt_match.group(1), alt_match.group(2).strip())]
            print(f"[GRAPH] Parsed tool_code format: {tool_calls}")
    
    if not tool_calls:
        return {"messages": []}
    
    user_id = state.get('user_id')
    user_location = state.get('user_location') or {}  # {lat, lon} from browser
    user_lat = user_location.get('lat', 0)
    user_lon = user_location.get('lon', 0)
    
    if user_lat and user_lon:
        print(f"[GRAPH] Using browser location: ({user_lat}, {user_lon})")
        
    for tool_name, args in tool_calls:
        tool_name = tool_name.strip()
        args = args.strip()
        
        if tool_name in TOOLS:
            tool_func = TOOLS[tool_name]
            try:
                # Handle specific args parsing
                if tool_name == "LOCATE":
                    # Parse: "hospital" or "hospital, Hamra" or "pharmacy, Beirut"
                    if "," in args:
                        facility_type, city = args.split(",", 1)
                        result = tool_func.invoke({
                            "facility_type": facility_type.strip(), 
                            "city": city.strip(),
                            "lat": user_lat,
                            "lon": user_lon
                        })
                    else:
                        # Use browser location if available, otherwise tool will fallback
                        result = tool_func.invoke({
                            "facility_type": args.strip(),
                            "lat": user_lat,
                            "lon": user_lon
                        })
                elif tool_name == "SEARCH_PHYSICIAN":
                    if "," in args:
                        name, clinic = args.split(",", 1)
                        result = tool_func.invoke({"name": name.strip(), "clinic": clinic.strip()})
                    else:
                        result = tool_func.invoke({"name": args.strip()})
                elif tool_name == "ALERT":
                    result = tool_func.invoke({"contact_number": "+96171186871", "message": args})
                elif tool_name == "READ_HISTORY":
                    result = tool_func.invoke({"query": args, "user_id": user_id})
                elif tool_name == "GET_PROFILE":
                    result = tool_func.invoke({"user_id": user_id})
                elif tool_name == "SAVE_PHYSICIAN":
                    # Simple parsing assuming comma separation
                    parts = [p.strip() for p in args.split(",")]
                    if len(parts) >= 4:
                        result = tool_func.invoke({"name": parts[0], "specialty": parts[1], "clinic": parts[2], "phone": parts[3], "user_id": user_id})
                    else:
                        result = f"Tool Error: Invalid arguments for SAVE_PHYSICIAN. Expected format: [SAVE_PHYSICIAN: Name, Specialty, Clinic, Phone]. You provided: {args}"
                elif tool_name == "BOOK_APPOINTMENT":
                    parts = [p.strip() for p in args.split(",")]
                    if len(parts) >= 2:
                        result = tool_func.invoke({"physician_name": parts[0], "time": parts[1], "user_id": user_id})
                    else:
                        result = tool_func.invoke({"physician_name": args.strip(), "time": "Unknown Time", "user_id": user_id})
                elif tool_name == "CALL_PHYSICIAN":
                    # Format: physician_name, phone_number, appointment_time
                    parts = [p.strip() for p in args.split(",")]
                    if len(parts) >= 3:
                        result = tool_func.invoke({
                            "physician_name": parts[0],
                            "physician_phone": parts[1],
                            "appointment_time": parts[2],
                            "user_id": user_id
                        })
                    else:
                        result = f"Tool Error: Invalid arguments for CALL_PHYSICIAN. Expected format: [CALL_PHYSICIAN: Name, Phone, Time]. You provided: {args}"
                elif tool_name == "ADD_CALENDAR":
                    parts = [p.strip() for p in args.split(",")]
                    if len(parts) >= 3:
                        result = tool_func.invoke({"summary": parts[0], "start_time": parts[1], "end_time": parts[2]})
                    else:
                        result = f"Tool Error: Invalid arguments for ADD_CALENDAR. Expected format: [ADD_CALENDAR: Summary, StartTime, EndTime]. You provided: {args}"
                elif tool_name == "GET_SUMMARIES":
                    days = int(args) if args.isdigit() else 7
                    result = tool_func.invoke({"days": days, "user_id": user_id})
                elif tool_name == "SAVE_SUMMARY":
                    # Generate and save daily summary - args can be date or empty for today
                    date_str = args.strip() if args and args.strip() else None
                    result = tool_func.invoke({"user_id": user_id, "date_str": date_str})
                elif tool_name == "ANALYZE_HEALTH":
                    # Comprehensive health topic analysis
                    result = tool_func.invoke({"topic": args.strip(), "user_id": user_id})
                elif tool_name == "WATCH_VITALS":
                    # Galaxy Watch real-time vitals
                    hours = int(args) if args.strip().isdigit() else 24
                    result = tool_func.invoke({"user_id": user_id, "hours": hours})
                elif tool_name == "GET_GOALS":
                    result = tool_func.invoke({"user_id": user_id})
                elif tool_name == "SET_GOAL":
                    result = tool_func.invoke({"description": args, "user_id": user_id})
                # Emergency Tools
                elif tool_name == "CHECK_VITALS":
                    parts = [p.strip() for p in args.split(",")]
                    hr = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
                    spo2 = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                    bp = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                    result = tool_func.invoke({"heart_rate": hr, "spo2": spo2, "blood_pressure_systolic": bp})
                elif tool_name == "FIND_HOSPITAL":
                    # Use browser location if available, otherwise city or default
                    result = tool_func.invoke({
                        "city": args.strip() if args else "Beirut",
                        "lat": user_lat if user_lat else None,
                        "lon": user_lon if user_lon else None
                    })
                elif tool_name == "DISPATCH_EMERGENCY":
                    parts = [p.strip() for p in args.split(",")]
                    if len(parts) >= 3:
                        result = tool_func.invoke({
                            "patient_name": parts[0],
                            "condition": parts[1],
                            "location": parts[2],
                            "user_id": user_id
                        })
                    else:
                        result = f"Tool Error: Invalid arguments for DISPATCH_EMERGENCY. Expected format: [DISPATCH_EMERGENCY: PatientName, Condition, Location]. You provided: {args}"
                elif tool_name == "EMERGENCY_RESPONSE":
                    parts = [p.strip() for p in args.split(",")]
                    hr = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
                    spo2 = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                    bp = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                    location = parts[3] if len(parts) > 3 else "Unknown"
                    result = tool_func.invoke({
                        "heart_rate": hr,
                        "spo2": spo2,
                        "blood_pressure_systolic": bp,
                        "patient_location": location,
                        "user_id": user_id
                    })
                # Emergency Call (Twilio)
                elif tool_name in ("EMERGENCY_CALL", "CALL_EMERGENCY"):
                    # Parse reason from args - format: [EMERGENCY_CALL: user_id, reason] or just [EMERGENCY_CALL: reason]
                    reason = args.strip() if args else "Emergency assistance requested"
                    result = tool_func.invoke({"user_id": user_id, "reason": reason})
                elif tool_name == "GET_EMERGENCY_CONTACTS":
                    result = tool_func.invoke({"user_id": user_id})
                # Advanced Tools
                elif tool_name == "SIMULATE_ECG":
                    parts = [p.strip() for p in args.split(",")]
                    duration = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 10
                    hr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 70
                    result = tool_func.invoke({"duration": duration, "heart_rate": hr})
                elif tool_name == "AWARD_XP":
                    result = tool_func.invoke({"task_name": args})
                elif tool_name == "GET_BRIEFING":
                    result = tool_func.invoke({"user_id": user_id})
                elif tool_name == "CHECK_SAFETY":
                    if "," in args:
                        med, symptom = args.split(",", 1)
                        result = tool_func.invoke({"med_name": med.strip(), "symptom": symptom.strip()})
                    else:
                        result = f"Tool Error: Invalid arguments for CHECK_SAFETY. Expected format: [CHECK_SAFETY: Medication, Symptom]. You provided: {args}"
                elif tool_name == "FIND_PROVIDERS":
                    if "," in args:
                        specialty, location = args.split(",", 1)
                        # Pass coordinates along with location name for better accuracy
                        result = tool_func.invoke({
                            "specialty": specialty.strip(), 
                            "location": location.strip(),
                            "lat": user_lat,
                            "lon": user_lon
                        })
                    else:
                        # Pass coordinates - tool will reverse geocode if needed
                        result = tool_func.invoke({
                            "specialty": args.strip(), 
                            "location": "",  # Let tool reverse geocode from coordinates
                            "lat": user_lat,
                            "lon": user_lon
                        })
                elif tool_name in ("SEARCH", "GUIDANCE", "SEARCH_PUBMED"):
                    result = tool_func.invoke({"query": args})
                elif tool_name == "MY_PHYSICIAN":
                    result = tool_func.invoke({"query": args})
                elif tool_name in ("LIFESTYLE_PLAN", "OPTIMIZE_LIFESTYLE"):
                    # Multi-agent lifestyle optimizer
                    result = tool_func.invoke({"user_id": user_id})
                else:
                    # Generic fallback - try to invoke with args as first param
                    result = tool_func.invoke({"args": args})
                    
                tool_result_msg = f"Tool Result ({tool_name}): {result}"
                print(f"[GRAPH DEBUG] Tool result: {tool_result_msg[:200]}...")
                new_messages.append(SystemMessage(content=tool_result_msg))
            except Exception as e:
                new_messages.append(SystemMessage(content=f"Tool Error ({tool_name}): {str(e)}"))
        else:
            new_messages.append(SystemMessage(content=f"Error: Tool {tool_name} not found."))
            
    return {"messages": new_messages}

def should_continue(state: AgentState):
    """
    Edge Logic: Decides whether to loop back to reasoning or end.
    """
    messages = state['messages']
    last_message = messages[-1]
    iterations = state.get('iterations', 0)
    content = last_message.content if isinstance(last_message, AIMessage) else ""
    
    if iterations > 5:
        print("[GRAPH] Max iterations reached.")
        return END
    
    if isinstance(last_message, AIMessage):
        # Check for [TOOL:] format
        if "[" in content and "]" in content:
            for tool_name in TOOLS:
                if f"[{tool_name}:" in content:
                    return "tools"
        
        # Check for ```tool_code format that Gemini uses
        if "```" in content:
            for tool_name in TOOLS:
                if f"{tool_name}:" in content:
                    print(f"[GRAPH] Detected tool_code format for {tool_name}")
                    return "tools"
    
    return END

# Build Graph
workflow = StateGraph(AgentState)

workflow.add_node("reasoning", reasoning_node)
workflow.add_node("tools", tool_execution_node)

workflow.set_entry_point("reasoning")

workflow.add_conditional_edges(
    "reasoning",
    should_continue,
    {
        "tools": "tools",
        END: END
    }
)

workflow.add_edge("tools", "reasoning")

app = workflow.compile()
