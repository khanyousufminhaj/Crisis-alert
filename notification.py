import streamlit as st
from twilio.rest import Client
from database import get_all_users
from utils import is_user_in_radius

def send_sms(to_number, message):
    """Send SMS using Twilio"""
    try:
        # Get Twilio credentials from Streamlit secrets
        account_sid = st.secrets["twilio"]["account_sid"]
        auth_token = st.secrets["twilio"]["auth_token"]
        twilio_number = st.secrets["twilio"]["phone_number"]
        
        # Initialize Twilio client
        client = Client(account_sid, auth_token)
        
        # Send message
        message = client.messages.create(
            body=message,
            from_=twilio_number,
            to=to_number
        )
        
        return True, message.sid
    except Exception as e:
        return False, str(e)

def notify_users_in_radius(alert):
    """
    Notify users who are within their specified radius of the crisis
    Returns tuples of (success, user_id, message) for each notification attempt
    """
    users = get_all_users()
    results = []
    
    for user in users:
        # Check if user is within their specified radius of the alert
        if is_user_in_radius(
            user['lat'], user['lon'], 
            alert['lat'], alert['lon'], 
            user['radius']
        ):
            # Create alert message
            message = (
                f"CRISIS ALERT: {alert['text'][:100]}... "
                f"Location: {alert['lat']:.4f}, {alert['lon']:.4f}. "
                f"Stay safe and follow official guidance."
            )
            
            # Send SMS notification
            success, msg_id = send_sms(user['phone'], message)
            results.append((success, user['id'], msg_id))
    
    return results
