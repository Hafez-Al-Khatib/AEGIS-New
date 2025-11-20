"""
Hospital Emergency Service Module
Handles emergency calls and nearest hospital location finding
"""
import os
from typing import Dict, Optional, List
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()

# Medical emergency severity levels
class EmergencySeverity:
    CRITICAL = "critical"      # Life-threatening
    HIGH = "high"              # Serious, needs urgent care
    MODERATE = "moderate"      # Should be seen soon
    LOW = "low"                # Non-urgent


class HospitalServiceManager:
    """
    Manages emergency hospital contact and location services
    """
    
    def __init__(self):
        self.geocoder = Nominatim(user_agent="aegis_health_monitor")
        self.emergency_service_number = os.getenv("EMERGENCY_SERVICE_NUMBER", "911")
        self.hospital_api_key = os.getenv("HOSPITAL_API_KEY", "")
        self.user_location_lat = None
        self.user_location_lon = None
        self.nearby_hospitals = []
        
    def set_user_location(self, latitude: float, longitude: float):
        """
        Set the user's current location
        
        Args:
            latitude: User's latitude coordinate
            longitude: User's longitude coordinate
        """
        self.user_location_lat = latitude
        self.user_location_lon = longitude
        print(f"User location set to: ({latitude}, {longitude})")
    
    def find_nearby_hospitals(self, radius_km: float = 10) -> List[Dict]:
        """
        Find hospitals near user's current location using Overpass API
        
        Args:
            radius_km: Search radius in kilometers
            
        Returns:
            List of nearby hospitals with details
        """
        if not self.user_location_lat or not self.user_location_lon:
            return [{"error": "User location not set"}]
        
        try:
            # Overpass API query to find hospitals
            query = f"""
            [bbox:{self.user_location_lon - 0.1},{self.user_location_lat - 0.1},
                    {self.user_location_lon + 0.1},{self.user_location_lat + 0.1}]
            (
              node["amenity"="hospital"];
              way["amenity"="hospital"];
              relation["amenity"="hospital"];
            );
            out center;
            """
            
            overpass_url = "http://overpass-api.de/api/interpreter"
            response = requests.post(overpass_url, data=query, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                hospitals = []
                
                for element in data.get("elements", []):
                    if "center" in element:
                        lat = element["center"]["lat"]
                        lon = element["center"]["lon"]
                    elif "lat" in element:
                        lat = element["lat"]
                        lon = element["lon"]
                    else:
                        continue
                    
                    distance = geodesic(
                        (self.user_location_lat, self.user_location_lon),
                        (lat, lon)
                    ).kilometers
                    
                    if distance <= radius_km:
                        hospital = {
                            "name": element.get("tags", {}).get("name", "Unknown Hospital"),
                            "latitude": lat,
                            "longitude": lon,
                            "distance_km": round(distance, 2),
                            "address": element.get("tags", {}).get("addr:full", "N/A"),
                            "phone": element.get("tags", {}).get("phone", "N/A"),
                            "emergency": element.get("tags", {}).get("emergency", "unknown")
                        }
                        hospitals.append(hospital)
                
                # Sort by distance
                hospitals.sort(key=lambda x: x["distance_km"])
                self.nearby_hospitals = hospitals
                return hospitals
            else:
                return [{"error": f"Failed to fetch hospitals: {response.status_code}"}]
                
        except Exception as e:
            return [{"error": f"Error finding hospitals: {str(e)}"}]
    
    def get_nearest_hospital(self) -> Optional[Dict]:
        """
        Get the single nearest hospital
        
        Returns:
            Nearest hospital info or None
        """
        if not self.nearby_hospitals:
            self.find_nearby_hospitals()
        
        return self.nearby_hospitals[0] if self.nearby_hospitals else None
    
    def call_emergency_services(self, 
                               user_id: int, 
                               user_email: str,
                               severity: str,
                               medical_summary: str,
                               latitude: Optional[float] = None,
                               longitude: Optional[float] = None) -> Dict:
        """
        Initiate emergency services call
        
        Args:
            user_id: User ID in system
            user_email: User email for contact
            severity: Emergency severity level
            medical_summary: Summary of medical issue
            latitude: Optional user latitude
            longitude: Optional user longitude
            
        Returns:
            Call result status
        """
        
        if latitude and longitude:
            self.set_user_location(latitude, longitude)
        
        # Find nearest hospital
        nearest_hospital = self.get_nearest_hospital()
        
        emergency_log = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "user_email": user_email,
            "severity": severity,
            "medical_summary": medical_summary,
            "user_location": {
                "latitude": self.user_location_lat,
                "longitude": self.user_location_lon
            },
            "nearest_hospital": nearest_hospital,
            "emergency_service_number": self.emergency_service_number,
            "status": "initiated"
        }
        
        try:
            # Simulate emergency service notification
            # In production, this would integrate with real emergency APIs
            print(f"\n{'='*60}")
            print("🚨 EMERGENCY ALERT INITIATED 🚨")
            print(f"{'='*60}")
            print(f"User: {user_email}")
            print(f"Severity: {severity}")
            print(f"Summary: {medical_summary}")
            print(f"Location: ({self.user_location_lat}, {self.user_location_lon})")
            
            if nearest_hospital:
                print(f"\n📍 Nearest Hospital: {nearest_hospital['name']}")
                print(f"   Distance: {nearest_hospital['distance_km']} km")
                print(f"   Phone: {nearest_hospital['phone']}")
                print(f"   Coordinates: ({nearest_hospital['latitude']}, {nearest_hospital['longitude']})")
            
            print(f"\n☎️  Emergency Service: {self.emergency_service_number}")
            print(f"{'='*60}\n")
            
            emergency_log["status"] = "success"
            return emergency_log
            
        except Exception as e:
            emergency_log["status"] = "failed"
            emergency_log["error"] = str(e)
            return emergency_log
    
    def create_emergency_contact_card(self, user_id: int, user_email: str) -> Dict:
        """
        Create emergency contact card with hospital info
        
        Args:
            user_id: User ID
            user_email: User email
            
        Returns:
            Emergency contact information
        """
        nearest = self.get_nearest_hospital()
        
        return {
            "user_id": user_id,
            "user_email": user_email,
            "emergency_number": self.emergency_service_number,
            "nearest_hospital": nearest,
            "all_nearby_hospitals": self.nearby_hospitals[:5],  # Top 5
            "user_location": {
                "latitude": self.user_location_lat,
                "longitude": self.user_location_lon
            },
            "created_at": datetime.now().isoformat()
        }


# Singleton instance
hospital_manager = HospitalServiceManager()
