import math
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

def geocode_address(address):
    """
    Convert an address string to latitude and longitude
    Returns a tuple (lat, lon) or None if geocoding fails
    """
    geolocator = Nominatim(user_agent="crisis_alert_app")
    try:
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        return None
    except (GeocoderTimedOut, GeocoderServiceError):
        return None

def is_user_in_radius(user_lat, user_lon, alert_lat, alert_lon, radius_km):
    """
    Check if a user is within the specified radius (in km) from an alert
    """
    distance = haversine_distance(user_lat, user_lon, alert_lat, alert_lon)
    return distance <= radius_km

def get_crisis_keywords():
    """
    Return a list of crisis-related keywords for filtering tweets
    """
    return [
        "earthquake", "fire", "flood", "hurricane", "tornado",
        "tsunami", "explosion", "shooting", "emergency", "evacuation",
        "disaster", "crisis", "accident", "collapsed", "trapped",
        "injured", "casualties", "warning", "alert", "danger"
    ]
