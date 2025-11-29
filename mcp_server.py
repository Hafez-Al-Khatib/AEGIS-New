from mcp.server.fastmcp import FastMCP
from tools import (
    search_medical_knowledge, 
    locate_nearest_facility, 
    trigger_emergency_alert, 
    search_physician, 
    search_my_physicians,
    read_medical_history
)

# Initialize FastMCP Server
mcp = FastMCP("Aegis Medical Tools")

@mcp.tool()
def search_medical_knowledge_tool(query: str) -> str:
    """
    Searches for medical information using PubMed NCBI API.
    Useful for finding peer-reviewed research on symptoms, treatments, and medical conditions.
    """
    return search_medical_knowledge(query)

@mcp.tool()
def locate_nearest_facility_tool(lat: float = 0.0, lon: float = 0.0, facility_type: str = "hospital") -> str:
    """
    Finds the nearest medical facility using OpenStreetMap (Nominatim).
    If lat/lon are 0, defaults to a demo location (Beirut).
    """
    return locate_nearest_facility(lat, lon, facility_type)

@mcp.tool()
def trigger_emergency_alert_tool(contact_number: str, message: str) -> str:
    """
    Sends an emergency SMS via Twilio if credentials exist.
    Otherwise, simulates the alert.
    Use this ONLY for CRITICAL risks.
    """
    return trigger_emergency_alert(contact_number, message)

@mcp.tool()
def search_physician_tool(name: str, clinic: str = "") -> str:
    """
    Searches for a physician's contact info using DuckDuckGo.
    Useful for finding public profiles of doctors mentioned in reports.
    """
    return search_physician(name, clinic)

@mcp.tool()
def search_my_physicians_tool(query: str) -> str:
    """
    Searches the user's PERSONAL address book (database) for a physician.
    Use this FIRST before searching online if the user asks about 'my doctor' or if a name matches.
    """
    return search_my_physicians(query)

@mcp.tool()
def read_medical_history_tool(query: str) -> str:
    """
    Searches the patient's past medical records (Knowledge Base) for specific keywords.
    Useful for answering questions about past conditions, medications, or test results.
    """
    return read_medical_history(query)

if __name__ == "__main__":
    mcp.run()
