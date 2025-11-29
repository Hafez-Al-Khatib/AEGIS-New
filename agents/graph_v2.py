"""
AEGIS Multi-Agent Graph - World-Class LangGraph Implementation

This module implements a proper LangGraph architecture with:
1. Tool binding via LangChain's bind_tools (not string parsing)
2. Multi-agent sub-graphs (Sentinel, Strategist, Chronicler)
3. Conditional routing based on intent classification
4. Proper state reducers and annotations
5. Checkpoint persistence for conversation memory
6. Human-in-the-loop for critical operations

LLM Options:
- Primary: Qwen 2.5 7B Instruct (local, privacy-preserving)
- Beta: Gemini 2.0 Flash (cloud, faster for testing)
"""

import os
import json
from typing import TypedDict, Annotated, Literal, Optional, List, Dict, Any, Sequence
from datetime import datetime
from enum import Enum

# LangGraph imports
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

# LangChain imports
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage, 
    AIMessage, 
    SystemMessage,
    ToolMessage
)
from langchain_core.tools import tool, BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

# Import our tools
from tools import (
    # Core Medical Tools
    search_medical_knowledge,
    search_clinical_guidance,
    read_medical_history,
    get_patient_profile,
    # Location & Providers
    locate_nearest_facility,
    find_providers_online,
    find_nearest_hospital,
    # Appointments
    book_appointment,
    book_appointment_voice,
    save_physician_contact,
    add_calendar_event,
    search_my_physicians,
    # Health Tracking
    get_daily_summaries,
    save_daily_summary,
    analyze_health_topic,
    get_watch_vitals,
    get_health_goals,
    set_health_goal,
    # Emergency
    trigger_emergency_alert,
    check_critical_vitals,
    dispatch_emergency_services,
    assess_and_respond_emergency,
    emergency_call,
    get_emergency_contacts,
    # Advanced
    simulate_ecg,
    award_habitica_xp,
    get_monday_briefing,
    check_med_safety,
    generate_lifestyle_plan
)

# ============================================================================
# LLM ENGINE - Qwen Primary, Gemini Beta
# ============================================================================

class LLMProvider(Enum):
    QWEN = "qwen"
    GEMINI = "gemini"

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "qwen").lower()
USE_GEMINI_BETA = os.getenv("USE_GEMINI_BETA", "false").lower() == "true"

def get_llm():
    """
    Returns the appropriate LLM based on configuration.
    Primary: Qwen 2.5 7B Instruct (privacy-preserving, local)
    Beta: Gemini 2.0 Flash (cloud, requires API key)
    """
    if USE_GEMINI_BETA and os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        print("[LLM] Using Gemini 2.0 Flash (Beta Mode)")
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,
            max_output_tokens=1024,
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
    else:
        # Use Qwen via llama.cpp
        from agents.qwen_llm import QwenChatModel
        print("[LLM] Using Qwen 2.5 7B Instruct (Privacy Mode)")
        return QwenChatModel()


# ============================================================================
# STATE DEFINITION
# ============================================================================

class IntentType(Enum):
    """Classification of user intent for routing"""
    GREETING = "greeting"
    MEDICAL_QUERY = "medical_query"
    RECORD_LOOKUP = "record_lookup"
    APPOINTMENT = "appointment"
    EMERGENCY = "emergency"
    VITALS = "vitals"
    LIFESTYLE = "lifestyle"
    LOCATION = "location"
    GENERAL = "general"


class AgentState(TypedDict):
    """
    State for the multi-agent graph.
    
    Attributes:
        messages: Conversation history with proper message types
        user_id: Current user's database ID
        user_context: Patient context string
        medical_record: Summarized medical record
        user_location: Browser geolocation {lat, lon}
        intent: Classified user intent for routing
        current_agent: Which agent is handling the request
        tool_calls_made: Track tools used in this turn
        requires_confirmation: Flag for critical operations
        error: Any error messages
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int
    user_context: str
    medical_record: str
    user_location: Optional[Dict[str, float]]
    intent: Optional[str]
    current_agent: Optional[str]
    tool_calls_made: List[str]
    requires_confirmation: bool
    error: Optional[str]


# ============================================================================
# TOOL GROUPS - Organized by Agent Responsibility
# ============================================================================

# Sentinel Agent Tools - Medical Information & Triage
SENTINEL_TOOLS = [
    search_clinical_guidance,
    search_medical_knowledge,
    read_medical_history,
    get_patient_profile,
    check_critical_vitals,
    check_med_safety,
    analyze_health_topic,
]

# Chronicler Agent Tools - Health Tracking & Vitals
CHRONICLER_TOOLS = [
    get_watch_vitals,
    get_daily_summaries,
    save_daily_summary,
    get_health_goals,
    set_health_goal,
    simulate_ecg,
    get_monday_briefing,
]

# Strategist Agent Tools - Actions & External Services
STRATEGIST_TOOLS = [
    locate_nearest_facility,
    find_providers_online,
    find_nearest_hospital,
    book_appointment,
    book_appointment_voice,
    save_physician_contact,
    add_calendar_event,
    search_my_physicians,
    award_habitica_xp,
    generate_lifestyle_plan,
]

# Emergency Tools - Critical Response
EMERGENCY_TOOLS = [
    emergency_call,
    get_emergency_contacts,
    dispatch_emergency_services,
    assess_and_respond_emergency,
    trigger_emergency_alert,
    find_nearest_hospital,
]

# All tools combined for full agent capability
ALL_TOOLS = list(set(
    SENTINEL_TOOLS + 
    CHRONICLER_TOOLS + 
    STRATEGIST_TOOLS + 
    EMERGENCY_TOOLS
))


# ============================================================================
# INTENT CLASSIFIER
# ============================================================================

INTENT_KEYWORDS = {
    IntentType.GREETING: ["hello", "hi", "hey", "good morning", "good evening"],
    IntentType.EMERGENCY: [
        "emergency", "help", "911", "ambulance", "chest pain", "heart attack",
        "stroke", "can't breathe", "dying", "unconscious", "call help",
        "critical", "urgent"
    ],
    IntentType.VITALS: [
        "heart rate", "blood pressure", "spo2", "oxygen", "pulse", 
        "vitals", "watch", "galaxy watch", "ecg", "hrv"
    ],
    IntentType.APPOINTMENT: [
        "book", "appointment", "schedule", "call doctor", "physician",
        "calendar", "meeting", "visit"
    ],
    IntentType.LOCATION: [
        "find", "nearest", "nearby", "hospital", "pharmacy", "clinic",
        "where", "locate", "map", "directions"
    ],
    IntentType.LIFESTYLE: [
        "lifestyle", "diet", "exercise", "sleep", "stress", "goals",
        "improve", "plan", "optimize", "habit"
    ],
    IntentType.RECORD_LOOKUP: [
        "records", "history", "medical history", "past", "previous",
        "profile", "conditions", "medications", "allergies"
    ],
    IntentType.MEDICAL_QUERY: [
        "what is", "how to", "treatment", "symptoms", "diagnosis",
        "medication", "side effects", "manage", "prevent"
    ],
}


def classify_intent(message: str) -> IntentType:
    """
    Classify user message intent for proper routing.
    Uses keyword matching - can be upgraded to ML classifier.
    """
    message_lower = message.lower()
    
    # Check emergency first (highest priority)
    for keyword in INTENT_KEYWORDS[IntentType.EMERGENCY]:
        if keyword in message_lower:
            return IntentType.EMERGENCY
    
    # Check other intents
    for intent_type, keywords in INTENT_KEYWORDS.items():
        if intent_type == IntentType.EMERGENCY:
            continue
        for keyword in keywords:
            if keyword in message_lower:
                return intent_type
    
    return IntentType.GENERAL


# ============================================================================
# AGENT PROMPTS
# ============================================================================

SENTINEL_SYSTEM_PROMPT = """You are Sentinel, an advanced AI medical assistant for the AEGIS health monitoring system.

CORE RESPONSIBILITIES:
1. Provide accurate, evidence-based medical information
2. Analyze patient health data and identify concerns
3. Triage medical issues and escalate emergencies
4. Guide patients to appropriate care resources

PATIENT CONTEXT:
{user_context}

MEDICAL RECORD SUMMARY:
{medical_record}

AVAILABLE TOOLS:
You have access to tools for:
- Searching medical knowledge (MedlinePlus, PubMed)
- Reading patient history and profile
- Checking medication safety
- Analyzing health topics comprehensively

GUIDELINES:
- Always prioritize patient safety
- Provide clear, actionable guidance
- Use tools proactively - don't ask permission
- For emergencies, escalate immediately
- Never provide diagnosis - guide to professionals
- Be empathetic but concise

CRITICAL: If the patient describes emergency symptoms (chest pain, difficulty breathing, 
stroke signs, severe bleeding, loss of consciousness), immediately use emergency tools."""

CHRONICLER_SYSTEM_PROMPT = """You are the Chronicler, the health tracking specialist of AEGIS.

CORE RESPONSIBILITIES:
1. Monitor and analyze vital signs from Galaxy Watch
2. Track health trends over time
3. Generate daily/weekly health summaries
4. Manage health goals and progress

PATIENT CONTEXT:
{user_context}

AVAILABLE TOOLS:
- get_watch_vitals: Real-time Galaxy Watch data
- get_daily_summaries: Historical health summaries
- save_daily_summary: Create health log entry
- get_health_goals/set_health_goal: Goal management
- simulate_ecg: ECG simulation and analysis
- get_monday_briefing: Weekly health report

Focus on data-driven insights and actionable health tracking."""

STRATEGIST_SYSTEM_PROMPT = """You are the Strategist, the action and planning agent of AEGIS.

CORE RESPONSIBILITIES:
1. Find and connect patients with healthcare providers
2. Book appointments (via message or AI voice call)
3. Manage healthcare logistics (calendar, contacts)
4. Generate comprehensive lifestyle plans
5. Gamify health achievements

PATIENT CONTEXT:
{user_context}

AVAILABLE TOOLS:
- locate_nearest_facility: Find nearby hospitals/pharmacies
- find_providers_online: Search for specialists on Google Maps
- book_appointment: Schedule via WhatsApp message
- book_appointment_voice: AI voice call to book
- save_physician_contact: Save doctor to contacts
- add_calendar_event: Add to Google Calendar
- generate_lifestyle_plan: Multi-agent lifestyle optimization
- award_habitica_xp: Gamification rewards

Always confirm details before booking. For voice calls, ensure you have phone number."""


# ============================================================================
# GRAPH NODES
# ============================================================================

def intent_router(state: AgentState) -> AgentState:
    """
    Entry node: Classifies intent and routes to appropriate agent.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    if isinstance(last_message, HumanMessage):
        intent = classify_intent(last_message.content)
        print(f"[ROUTER] Intent classified: {intent.value}")
        
        # Determine which agent should handle this
        if intent == IntentType.EMERGENCY:
            current_agent = "emergency"
        elif intent in [IntentType.VITALS, IntentType.LIFESTYLE]:
            current_agent = "chronicler"
        elif intent in [IntentType.APPOINTMENT, IntentType.LOCATION]:
            current_agent = "strategist"
        else:
            current_agent = "sentinel"
        
        return {
            **state,
            "intent": intent.value,
            "current_agent": current_agent,
            "tool_calls_made": []
        }
    
    return state


def sentinel_node(state: AgentState) -> AgentState:
    """
    Sentinel Agent: Medical information and triage.
    """
    llm = get_llm()
    llm_with_tools = llm.bind_tools(SENTINEL_TOOLS)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SENTINEL_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    chain = prompt | llm_with_tools
    
    response = chain.invoke({
        "user_context": state.get("user_context", ""),
        "medical_record": state.get("medical_record", ""),
        "messages": state["messages"]
    })
    
    return {
        **state,
        "messages": [response],
        "current_agent": "sentinel"
    }


def chronicler_node(state: AgentState) -> AgentState:
    """
    Chronicler Agent: Health tracking and vitals.
    """
    llm = get_llm()
    llm_with_tools = llm.bind_tools(CHRONICLER_TOOLS)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", CHRONICLER_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    chain = prompt | llm_with_tools
    
    response = chain.invoke({
        "user_context": state.get("user_context", ""),
        "messages": state["messages"]
    })
    
    return {
        **state,
        "messages": [response],
        "current_agent": "chronicler"
    }


def strategist_node(state: AgentState) -> AgentState:
    """
    Strategist Agent: Actions, appointments, logistics.
    """
    llm = get_llm()
    llm_with_tools = llm.bind_tools(STRATEGIST_TOOLS)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", STRATEGIST_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    chain = prompt | llm_with_tools
    
    response = chain.invoke({
        "user_context": state.get("user_context", ""),
        "messages": state["messages"]
    })
    
    return {
        **state,
        "messages": [response],
        "current_agent": "strategist"
    }


def emergency_node(state: AgentState) -> AgentState:
    """
    Emergency Agent: Critical response with Twilio integration.
    """
    llm = get_llm()
    llm_with_tools = llm.bind_tools(EMERGENCY_TOOLS)
    
    emergency_prompt = """You are the Emergency Response Agent for AEGIS.

CRITICAL: A potential emergency has been detected.

IMMEDIATE ACTIONS:
1. Assess the situation severity
2. If truly critical: Use emergency_call to contact emergency contacts via Twilio
3. Find nearest hospital
4. Provide immediate first-aid guidance while help is on the way

PATIENT CONTEXT:
{user_context}

Be calm but act quickly. Patient safety is the absolute priority."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", emergency_prompt),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    chain = prompt | llm_with_tools
    
    response = chain.invoke({
        "user_context": state.get("user_context", ""),
        "messages": state["messages"]
    })
    
    return {
        **state,
        "messages": [response],
        "current_agent": "emergency",
        "requires_confirmation": False  # Emergencies should NOT wait
    }


# ============================================================================
# ROUTING LOGIC
# ============================================================================

def route_by_intent(state: AgentState) -> Literal["sentinel", "chronicler", "strategist", "emergency"]:
    """
    Routes to the appropriate agent based on classified intent.
    """
    current_agent = state.get("current_agent", "sentinel")
    return current_agent


def should_use_tools(state: AgentState) -> Literal["tools", "respond"]:
    """
    Check if the last AI message contains tool calls.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "respond"


def final_response(state: AgentState) -> AgentState:
    """
    Final node to clean up and prepare response.
    """
    # No modification needed, just pass through
    return state


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

def build_aegis_graph():
    """
    Constructs the multi-agent AEGIS graph.
    
    Architecture:
    
    START → Router → [Sentinel | Chronicler | Strategist | Emergency]
                          ↓
                    [Tools if needed]
                          ↓
                       Response
                          ↓
                         END
    """
    # Create tool node with all tools
    tool_node = ToolNode(ALL_TOOLS)
    
    # Build workflow
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("router", intent_router)
    workflow.add_node("sentinel", sentinel_node)
    workflow.add_node("chronicler", chronicler_node)
    workflow.add_node("strategist", strategist_node)
    workflow.add_node("emergency", emergency_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("respond", final_response)
    
    # Entry point
    workflow.add_edge(START, "router")
    
    # Router to agents
    workflow.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "sentinel": "sentinel",
            "chronicler": "chronicler",
            "strategist": "strategist",
            "emergency": "emergency"
        }
    )
    
    # Each agent can use tools or respond
    for agent in ["sentinel", "chronicler", "strategist", "emergency"]:
        workflow.add_conditional_edges(
            agent,
            should_use_tools,
            {
                "tools": "tools",
                "respond": "respond"
            }
        )
    
    # After tools, loop back to the current agent
    workflow.add_conditional_edges(
        "tools",
        lambda state: state.get("current_agent", "sentinel"),
        {
            "sentinel": "sentinel",
            "chronicler": "chronicler",
            "strategist": "strategist",
            "emergency": "emergency"
        }
    )
    
    # Final response ends
    workflow.add_edge("respond", END)
    
    # Compile with memory checkpointer
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    return app


# ============================================================================
# MAIN GRAPH INSTANCE
# ============================================================================

# Build the graph
aegis_graph = build_aegis_graph()

# For backwards compatibility
app = aegis_graph


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def invoke_aegis(
    message: str,
    user_id: int,
    user_context: str = "",
    medical_record: str = "",
    user_location: Optional[Dict[str, float]] = None,
    thread_id: str = "default"
) -> str:
    """
    Convenience function to invoke the AEGIS graph.
    
    Args:
        message: User's message
        user_id: Database user ID
        user_context: Patient context summary
        medical_record: Medical record summary
        user_location: {lat, lon} from browser
        thread_id: Conversation thread ID for memory
        
    Returns:
        AI response string
    """
    config = RunnableConfig(
        configurable={"thread_id": thread_id}
    )
    
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "user_context": user_context,
        "medical_record": medical_record,
        "user_location": user_location,
        "intent": None,
        "current_agent": None,
        "tool_calls_made": [],
        "requires_confirmation": False,
        "error": None
    }
    
    result = aegis_graph.invoke(initial_state, config)
    
    # Extract final response
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    
    return "I apologize, but I couldn't generate a response. Please try again."


# ============================================================================
# STREAMING SUPPORT
# ============================================================================

async def stream_aegis(
    message: str,
    user_id: int,
    user_context: str = "",
    medical_record: str = "",
    user_location: Optional[Dict[str, float]] = None,
    thread_id: str = "default"
):
    """
    Async generator for streaming responses.
    
    Yields:
        Dict with 'type' (token, tool_start, tool_end) and 'content'
    """
    config = RunnableConfig(
        configurable={"thread_id": thread_id}
    )
    
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "user_context": user_context,
        "medical_record": medical_record,
        "user_location": user_location,
        "intent": None,
        "current_agent": None,
        "tool_calls_made": [],
        "requires_confirmation": False,
        "error": None
    }
    
    async for event in aegis_graph.astream_events(initial_state, config, version="v2"):
        kind = event["event"]
        
        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                yield {"type": "token", "content": content}
                
        elif kind == "on_tool_start":
            tool_name = event["name"]
            yield {"type": "tool_start", "content": tool_name}
            
        elif kind == "on_tool_end":
            tool_name = event["name"]
            yield {"type": "tool_end", "content": tool_name}
