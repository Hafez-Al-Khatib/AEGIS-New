import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Navigation, Phone, Star, Clock, X } from 'lucide-react';

// Fix for default marker icons in React-Leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// Custom marker icons
const createCustomIcon = (color) => {
    return L.divIcon({
        className: 'custom-marker',
        html: `<div style="
            background: ${color};
            width: 32px;
            height: 32px;
            border-radius: 50% 50% 50% 0;
            transform: rotate(-45deg);
            border: 3px solid white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        "><div style="
            width: 10px;
            height: 10px;
            background: white;
            border-radius: 50%;
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        "></div></div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 32],
        popupAnchor: [0, -32],
    });
};

const hospitalIcon = createCustomIcon('#ef4444');  // Red
const pharmacyIcon = createCustomIcon('#22c55e');  // Green
const doctorIcon = createCustomIcon('#3b82f6');    // Blue
const defaultIcon = createCustomIcon('#8b5cf6');   // Purple

// Component to fit map bounds to markers
function FitBounds({ locations }) {
    const map = useMap();
    
    useEffect(() => {
        if (locations.length > 0) {
            const bounds = L.latLngBounds(locations.map(loc => [loc.lat, loc.lng]));
            map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
        }
    }, [locations, map]);
    
    return null;
}

// Parse location data from tool response
export function parseLocationResponse(content) {
    const locations = [];
    
    // Parse navigation links: https://www.google.com/maps/dir/?api=1&origin=LAT,LNG&destination=LAT,LNG
    const navLinkPattern = /\[Navigate[^\]]*\]\((https:\/\/www\.google\.com\/maps\/dir\/[^)]+)\)/g;
    const namePattern = /\d+\.\s+\*\*([^*]+)\*\*\s*\(([^)]+)\)/g;
    const addressPattern = /📍\s+([^\n]+)/g;
    
    // Extract names, ratings, and status
    const entries = content.split(/(?=\d+\.\s+\*\*)/);
    
    entries.forEach((entry, index) => {
        if (!entry.trim()) return;
        
        // Extract name and rating
        const nameMatch = entry.match(/\d+\.\s+\*\*([^*]+)\*\*\s*\(([^⭐]+)⭐?\)/);
        const addressMatch = entry.match(/📍\s+([^\n]+)/);
        const navMatch = entry.match(/destination=([0-9.-]+),([0-9.-]+)/);
        const isOpen = entry.includes('🟢');
        const isClosed = entry.includes('🔴');
        
        if (nameMatch && navMatch) {
            locations.push({
                id: index,
                name: nameMatch[1].trim(),
                rating: nameMatch[2].trim(),
                address: addressMatch ? addressMatch[1].trim() : 'Address not available',
                lat: parseFloat(navMatch[1]),
                lng: parseFloat(navMatch[2]),
                isOpen: isOpen ? true : (isClosed ? false : null),
                navLink: entry.match(/\(https:\/\/www\.google\.com\/maps[^)]+\)/)?.[0]?.slice(1, -1) || null
            });
        }
    });
    
    return locations;
}

// Determine icon based on facility type
function getMarkerIcon(content) {
    const lowerContent = content.toLowerCase();
    if (lowerContent.includes('hospital') || lowerContent.includes('emergency')) return hospitalIcon;
    if (lowerContent.includes('pharmacy')) return pharmacyIcon;
    if (lowerContent.includes('doctor') || lowerContent.includes('clinic')) return doctorIcon;
    return defaultIcon;
}

// User location marker (blue pulsing dot)
const userLocationIcon = L.divIcon({
    className: 'user-location-marker',
    html: `<div style="
        width: 20px;
        height: 20px;
        background: #3b82f6;
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 0 0 8px rgba(59, 130, 246, 0.3), 0 2px 8px rgba(0,0,0,0.3);
        animation: pulse 2s infinite;
    "></div>
    <style>
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4), 0 2px 8px rgba(0,0,0,0.3); }
            70% { box-shadow: 0 0 0 15px rgba(59, 130, 246, 0), 0 2px 8px rgba(0,0,0,0.3); }
            100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0), 0 2px 8px rgba(0,0,0,0.3); }
        }
    </style>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
});

// Extract user origin from navigation links
function extractUserOrigin(content) {
    const match = content.match(/origin=([0-9.-]+),([0-9.-]+)/);
    if (match) {
        return { lat: parseFloat(match[1]), lng: parseFloat(match[2]) };
    }
    return null;
}

export default function MapView({ content, onClose, userLocation }) {
    const rawLocations = parseLocationResponse(content);
    const mapRef = useRef(null);
    
    // Validate coordinate helper
    const isValidCoord = (coord) => {
        return coord && 
               typeof coord.lat === 'number' && 
               typeof coord.lng === 'number' && 
               !isNaN(coord.lat) && 
               !isNaN(coord.lng) &&
               coord.lat !== 0 && 
               coord.lng !== 0;
    };
    
    // Filter out any locations with invalid coordinates
    const locations = rawLocations.filter(loc => isValidCoord(loc));
    
    // Try to get user location from props or extract from nav links
    // Note: userLocation from ChatInterface uses "lon", but nav links use "lng"
    const extractedOrigin = extractUserOrigin(content);
    const userOrigin = userLocation 
        ? { lat: userLocation.lat, lng: userLocation.lon || userLocation.lng }
        : extractedOrigin;
    
    // Debug logging
    console.log('[MapView] userLocation prop:', userLocation);
    console.log('[MapView] userOrigin computed:', userOrigin);
    console.log('[MapView] valid locations:', locations.length);
    
    if (locations.length === 0) {
        console.warn('[MapView] No valid locations found in content');
        return null;
    }
    
    // Calculate center - prefer user location, fallback to average of results
    const center = (userOrigin && isValidCoord(userOrigin))
        ? [userOrigin.lat, userOrigin.lng]
        : locations.length > 0 
            ? [
                locations.reduce((sum, loc) => sum + loc.lat, 0) / locations.length,
                locations.reduce((sum, loc) => sum + loc.lng, 0) / locations.length
              ]
            : [33.8938, 35.5018]; // Default to Beirut
    
    console.log('[MapView] center:', center);
    
    // Final safety check - ensure center coordinates are valid numbers
    if (!center || !Array.isArray(center) || center.length !== 2 || 
        typeof center[0] !== 'number' || typeof center[1] !== 'number' ||
        isNaN(center[0]) || isNaN(center[1])) {
        console.error('[MapView] Invalid center coordinates:', center);
        return (
            <div className="p-4 bg-slate-800 rounded-xl text-slate-400 text-sm">
                Unable to display map - invalid coordinates
            </div>
        );
    }
    
    const icon = getMarkerIcon(content);
    
    return (
        <div className="relative w-full h-80 rounded-xl overflow-hidden border border-slate-600 shadow-lg">
            {/* Close button */}
            {onClose && (
                <button 
                    onClick={onClose}
                    className="absolute top-2 right-2 z-[1000] bg-slate-800/90 hover:bg-slate-700 text-white p-1.5 rounded-full transition-colors"
                >
                    <X size={16} />
                </button>
            )}
            
            <MapContainer
                ref={mapRef}
                center={center}
                zoom={13}
                style={{ height: '100%', width: '100%' }}
                className="z-0"
            >
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                
                <FitBounds locations={userOrigin && isValidCoord(userOrigin) ? [...locations, {lat: userOrigin.lat, lng: userOrigin.lng}] : locations} />
                
                {/* User location marker */}
                {userOrigin && isValidCoord(userOrigin) && (
                    <Marker 
                        position={[userOrigin.lat, userOrigin.lng]}
                        icon={userLocationIcon}
                    >
                        <Popup>
                            <div className="text-center p-1">
                                <strong className="text-slate-900">📍 Your Location</strong>
                            </div>
                        </Popup>
                    </Marker>
                )}
                
                {/* Facility markers */}
                {locations.map((location) => (
                    <Marker 
                        key={location.id} 
                        position={[location.lat, location.lng]}
                        icon={icon}
                    >
                        <Popup className="custom-popup">
                            <div className="min-w-[200px] p-1">
                                <h3 className="font-bold text-slate-900 text-sm mb-1">
                                    {location.name}
                                </h3>
                                
                                <div className="flex items-center gap-2 text-xs text-slate-600 mb-1">
                                    <Star size={12} className="text-yellow-500" />
                                    <span>{location.rating}</span>
                                    {location.isOpen !== null && (
                                        <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                                            location.isOpen 
                                                ? 'bg-green-100 text-green-700' 
                                                : 'bg-red-100 text-red-700'
                                        }`}>
                                            {location.isOpen ? 'Open' : 'Closed'}
                                        </span>
                                    )}
                                </div>
                                
                                <p className="text-xs text-slate-500 mb-2">
                                    {location.address}
                                </p>
                                
                                {location.navLink && (
                                    <a 
                                        href={location.navLink}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 px-2 py-1 bg-blue-500 hover:bg-blue-600 text-white text-xs rounded transition-colors"
                                    >
                                        <Navigation size={12} />
                                        Navigate
                                    </a>
                                )}
                            </div>
                        </Popup>
                    </Marker>
                ))}
            </MapContainer>
            
            {/* Legend */}
            <div className="absolute bottom-2 left-2 z-[1000] bg-slate-800/90 backdrop-blur-sm rounded-lg px-3 py-2 text-xs text-white">
                <span className="font-medium">{locations.length} location{locations.length > 1 ? 's' : ''} found</span>
            </div>
        </div>
    );
}
