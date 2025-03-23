import streamlit as st
import pandas as pd
import threading
import time
import io
import traceback
from datetime import datetime
import numpy as np
import pickle
from database import (
    init_db, get_potential_alerts, update_alert_status, 
    register_user, get_alert_by_id
)
from twitter_stream import create_twitter_stream_thread
from notification import notify_users_in_radius
from opencage.geocoder import OpenCageGeocode
from opencage.geocoder import InvalidInputError, RateLimitExceededError, UnknownError
from twilio.rest import Client

print("Application starting")

# Initialize the database
init_db()
print("Database initialized")

# Page configuration
st.set_page_config(page_title="Crisis Alert System", layout="wide")
print("Streamlit page configured")

def initialize_session_state():
    """Initialize session state variables"""
    if 'twitter_stream_active' not in st.session_state:
        st.session_state.twitter_stream_active = False
    if 'twitter_thread' not in st.session_state:
        st.session_state.twitter_thread = None
    if 'twitter_stop_event' not in st.session_state:
        st.session_state.twitter_stop_event = None
    if 'selected_location' not in st.session_state:
        st.session_state.selected_location = {"lat": 22.5726459, "lon": 88.3638953}
    if 'location_selected' not in st.session_state:
        st.session_state.location_selected = False
    if 'geocoded_address' not in st.session_state:
        st.session_state.geocoded_address = None
    if 'geocoding_error' not in st.session_state:
        st.session_state.geocoding_error = None
    if 'test_tweet_lat' not in st.session_state:
        st.session_state.test_tweet_lat = 22.5726459
    if 'test_tweet_lon' not in st.session_state:
        st.session_state.test_tweet_lon = 88.3638953
    if 'test_tweet_location_desc' not in st.session_state:
        st.session_state.test_tweet_location_desc = "Default location"
    if 'editing_alert_id' not in st.session_state:
        st.session_state.editing_alert_id = None
    if 'editing_alert_text' not in st.session_state:
        st.session_state.editing_alert_text = ""
    if 'edit_mode' not in st.session_state:
        st.session_state.edit_mode = False
    if 'tweet_is_disaster' not in st.session_state:
        st.session_state.tweet_is_disaster = False
    if 'current_tweet_text' not in st.session_state:
        st.session_state.current_tweet_text = ""

initialize_session_state()

def start_twitter_stream():
    """Start the Twitter streaming thread"""
    if not st.session_state.twitter_stream_active:
        print("Starting Twitter stream")
        thread, stop_event = create_twitter_stream_thread()
        thread.start()
        st.session_state.twitter_thread = thread
        st.session_state.twitter_stop_event = stop_event
        st.session_state.twitter_stream_active = True
        print("Twitter stream started successfully")
        st.success("Twitter stream started!")
    else:
        print("Twitter stream start requested but stream is already running")
        st.info("Twitter stream is already running.")

def stop_twitter_stream():
    """Stop the Twitter streaming thread"""
    if st.session_state.twitter_stream_active and st.session_state.twitter_stop_event:
        print("Stopping Twitter stream")
        st.session_state.twitter_stop_event.set()
        st.session_state.twitter_stream_active = False
        print("Twitter stream stopped successfully")
        st.success("Twitter stream stopped!")
    else:
        print("Twitter stream stop requested but no active stream found")
        st.info("Twitter stream is not running.")

def confirm_alert(alert_id):
    """Confirm crisis alert and notify users"""
    print(f"Preparing to edit message for alert with ID: {alert_id}")
    alert = get_alert_by_id(alert_id)
    if alert:
        if not st.session_state.edit_mode:
            st.session_state.editing_alert_id = alert_id
            st.session_state.editing_alert_text = alert['text']
            st.session_state.edit_mode = True
            st.rerun()
        else:
            update_alert_status(alert_id, 'confirmed')
            print(f"Alert {alert_id} status updated to 'confirmed'")
            
            alert['text'] = st.session_state.editing_alert_text
            notification_results = notify_users_in_radius(alert)
            st.session_state.notification_results = notification_results
            print(f"Sent {len(notification_results)} notifications for alert {alert_id} with edited message")
            
            st.session_state.edit_mode = False
            st.session_state.editing_alert_id = None
            st.session_state.editing_alert_text = ""
            
            st.success(f"Alert confirmed! Sent {len(notification_results)} notifications.")
            st.rerun()
    else:
        print(f"Failed to confirm alert: Alert with ID {alert_id} not found")
        st.error("Alert not found!")

def dismiss_alert(alert_id):
    """Dismiss a potential alert"""
    print(f"Dismissing alert with ID: {alert_id}")
    update_alert_status(alert_id, 'dismissed')
    print(f"Alert {alert_id} status updated to 'dismissed'")
    st.success("Alert dismissed!")

def geocode_address(address):
    """Convert address to geocoordinates using OpenCage API"""
    print(f"Geocoding address: {address}")
    
    key = st.secrets["OpenCage"]["api_key"]
    geocoder = OpenCageGeocode(key)
    
    try:
        results = geocoder.geocode(address)
        if results and len(results):
            result = results[0]
            lat = result['geometry']['lat']
            lon = result['geometry']['lng']
            formatted_address = result['formatted']
            
            print(f"Geocoded {address} to: {lat}, {lon}")
            print(f"Formatted address: {formatted_address}")
            
            st.session_state.selected_location = {"lat": lat, "lon": lon}
            st.session_state.geocoded_address = formatted_address
            st.session_state.location_selected = True
            st.session_state.geocoding_error = None
            
            return lat, lon, formatted_address
        else:
            print(f"No geocoding results for address: {address}")
            st.session_state.geocoding_error = "Could not find coordinates for this address"
            st.session_state.location_selected = False
            return None, None, None
            
    except RateLimitExceededError as ex:
        print(f"OpenCage rate limit exceeded: {str(ex)}")
        st.session_state.geocoding_error = "Geocoding service rate limit exceeded. Please try again later."
        st.session_state.location_selected = False
        return None, None, None
    except InvalidInputError as ex:
        print(f"OpenCage invalid input: {str(ex)}")
        st.session_state.geocoding_error = f"Invalid address input: {str(ex)}"
        st.session_state.location_selected = False
        return None, None, None
    except Exception as ex:
        print(f"Geocoding error: {str(ex)}")
        st.session_state.geocoding_error = f"Geocoding error: {str(ex)}"
        st.session_state.location_selected = False
        return None, None, None

def load_model():
    """Load the disaster prediction model and vectorizer"""
    try:
        model = pickle.load(open('model.pkl', 'rb'))
        vectorizer = pickle.load(open('vectorizer.pkl', 'rb'))
        return model, vectorizer
    except (FileNotFoundError, pickle.UnpicklingError):
        st.warning("Model files not found or corrupted.")
        return None, None

def check_tweet(text, model, vectorizer):
    """Predict if a tweet is about a disaster"""
    if not text:
        return st.warning("Please enter a tweet to analyze")
    
    X_test = vectorizer.transform([text])
    prediction = model.predict(X_test)[0]
    
    if prediction == 1:
        st.session_state.tweet_is_disaster = True
        st.session_state.current_tweet_text = text
        st.write('### This tweet likely refers to an actual disaster')
        return True
    else:
        st.session_state.tweet_is_disaster = False
        st.write("### This tweet likely doesn't refer to an actual disaster")
        return False

# Sidebar with app controls
st.sidebar.title("Crisis Alert System")

st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "User Registration"])

if page == "Dashboard":
    st.title("Crisis Alert Dashboard")
    
    col1, col2, col3 = st.columns([2, 2, 6])
    with col1:
        if st.button("Start Stream", key="start_stream"):
            start_twitter_stream()
    with col2:
        if st.button("Stop Stream", key="stop_stream"):
            stop_twitter_stream()
    
    if not st.session_state.twitter_stream_active:
        st.warning("Twitter stream is not active. Start the stream to monitor for crisis events or enter a test tweet to check functionality.")
    else:
        st.success("Twitter stream is active and monitoring for potential crises.")
    
    dashboard_tab1, dashboard_tab2, dashboard_tab3 = st.tabs(["Potential Alerts", "Create Test Alert", "Test Tweet"])
    
    with dashboard_tab1:
        st.header("Potential Crisis Alerts")
        
        if st.session_state.edit_mode and st.session_state.editing_alert_id:
            alert = get_alert_by_id(st.session_state.editing_alert_id)
            if alert:
                st.info(f"Editing message for Alert #{st.session_state.editing_alert_id}")
                
                with st.form("edit_alert_message_form"):
                    edited_message = st.text_area(
                        "Edit Alert Message", 
                        value=st.session_state.editing_alert_text,
                        height=100,
                        help="Edit the message that will be sent to users in the affected area"
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        submit_button = st.form_submit_button("Confirm & Send Alert", type="primary")
                        if submit_button:
                            st.session_state.editing_alert_text = edited_message
                            confirm_alert(st.session_state.editing_alert_id)
                    
                    with col2:
                        cancel_button = st.form_submit_button("Cancel")
                        if cancel_button:
                            st.session_state.edit_mode = False
                            st.session_state.editing_alert_id = None
                            st.session_state.editing_alert_text = ""
                            st.rerun()
                
                if edited_message != alert['text']:
                    with st.expander("Compare Changes"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**Original Message:**")
                            st.info(alert['text'])
                        with col2:
                            st.write("**Edited Message:**")
                            st.success(edited_message)
            else:
                st.error("Alert not found. Please try again.")
                st.session_state.edit_mode = False
                st.session_state.editing_alert_id = None
                st.rerun()
        else:
            alerts = get_potential_alerts()
            
            if alerts:
                map_data = pd.DataFrame({
                    'lat': [alert['lat'] for alert in alerts],
                    'lon': [alert['lon'] for alert in alerts]
                })
                
                st.map(map_data)
                
                for alert in alerts:
                    with st.expander(f"Alert ID: {alert['id']} - {alert['text'][:50]}..."):
                        st.write(f"**Text:** {alert['text']}")
                        st.write(f"**Location:** Lat {alert['lat']:.6f}, Lon {alert['lon']:.6f}")
                        st.write(f"**Time:** {alert['time']}")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Edit & Confirm", key=f"confirm_{alert['id']}"):
                                confirm_alert(alert['id'])
                        with col2:
                            if st.button("Dismiss Alert", key=f"dismiss_{alert['id']}"):
                                dismiss_alert(alert['id'])
                                st.rerun()
            else:
                st.info("No potential crisis alerts to review at this time.")
        
        if 'notification_results' in st.session_state and st.session_state.notification_results:
            st.header("Notification Results")
            for result in st.session_state.notification_results:
                success, user_id, message = result
                status = "✅ Sent" if success else "❌ Failed"
                st.write(f"{status} - User ID: {user_id}, Message ID: {message}")
    
    with dashboard_tab2:
        st.header("Test SMS Notification System")
        st.info("Use this form to generate a test alert and trigger notifications.")
        
        with st.form("test_alert_form"):
            test_alert_text = st.text_area("Alert Message", 
                                        value="This is a TEST crisis alert. Please ignore.",
                                        help="Enter the alert message text")
            
            st.write("**Alert Location**")
            col1, col2 = st.columns(2)
            with col1:
                test_lat = st.number_input("Latitude", value=22.5726459, format="%.6f",
                                        help="Enter the latitude for the test alert")
            with col2:
                test_lon = st.number_input("Longitude", value=88.3638953, format="%.6f",
                                        help="Enter the longitude for the test alert")
            
            address_lookup = st.checkbox("Use address lookup instead")
            
            if address_lookup:
                test_address = st.text_input("Address for Alert", 
                                        help="Enter an address to geocode for the test alert")
            
            submitted = st.form_submit_button("Generate Test Alert")
            
            if submitted:
                if address_lookup and test_address:
                    with st.spinner("Geocoding address..."):
                        lat, lon, formatted_address = geocode_address(test_address)
                        if lat and lon:
                            test_lat = lat
                            test_lon = lon
                            st.success(f"Using location: {formatted_address}")
                        else:
                            st.error("Could not geocode that address. Using default coordinates.")
                
                import sqlite3
                from datetime import datetime
                
                conn = sqlite3.connect('crisis_alerts.db')
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO alerts (text, lat, lon, time, status)
                    VALUES (?, ?, ?, ?, ?)
                ''', (test_alert_text, test_lat, test_lon, datetime.now().isoformat(), 'pending'))
                
                alert_id = cursor.lastrowid
                conn.commit()
                conn.close()
                
                st.success(f"Test alert created with ID: {alert_id}")
                st.info("Click 'Edit & Send' to customize and send the notification")
                
                if st.button("Edit & Send", key=f"edit_send_{alert_id}"):
                    confirm_alert(alert_id)
    
    with dashboard_tab3:
        st.header("Tweet Disaster Analysis")
        
        st.info("""
        This tool helps you analyze tweets to determine if they're about real disasters.
        You can use it to test how the system detects crisis-related content.
        """)
        
        model, vectorizer = load_model()
        
        if model is not None and vectorizer is not None:
            if st.session_state.tweet_is_disaster:
                st.success("✅ Tweet classified as a potential disaster. Please specify location:")
                
                st.markdown("### Tweet Text:")
                st.info(st.session_state.current_tweet_text)
                
                st.subheader("Specify location for this disaster")
                location_col1, location_col2 = st.columns(2)
                
                with location_col1:
                    location_input_method = st.radio(
                        "Location method",
                        ["Enter Coordinates", "Enter Address"],
                        index=0,
                        help="Choose how to specify the location for this disaster"
                    )
                
                if location_input_method == "Enter Coordinates":
                    coord_col1, coord_col2 = st.columns(2)
                    with coord_col1:
                        input_lat = st.number_input("Latitude", value=st.session_state.test_tweet_lat, format="%.6f")
                    with coord_col2:
                        input_lon = st.number_input("Longitude", value=st.session_state.test_tweet_lon, format="%.6f")
                    
                    if input_lat != st.session_state.test_tweet_lat or input_lon != st.session_state.test_tweet_lon:
                        st.session_state.test_tweet_lat = input_lat
                        st.session_state.test_tweet_lon = input_lon
                        st.session_state.test_tweet_location_desc = f"Coordinates (Lat: {input_lat:.6f}, Lon: {input_lon:.6f})"
                
                elif location_input_method == "Enter Address":
                    test_address = st.text_input("Address", 
                                              placeholder="e.g., 123 Main St, New York, NY",
                                              help="Enter an address for the disaster location")
                    
                    if st.button("Geocode Address"):
                        if test_address:
                            with st.spinner("Looking up address..."):
                                lat, lon, formatted_address = geocode_address(test_address)
                                if lat and lon:
                                    st.session_state.test_tweet_lat = lat
                                    st.session_state.test_tweet_lon = lon
                                    st.session_state.test_tweet_location_desc = formatted_address
                                    st.success(f"Using location: {formatted_address}")
                                else:
                                    st.error("Could not geocode address. Using default location.")
                        else:
                            st.warning("Please enter an address to geocode.")
                
                st.info(f"Current location: {st.session_state.test_tweet_location_desc} (Lat: {st.session_state.test_tweet_lat:.6f}, Lon: {st.session_state.test_tweet_lon:.6f})")
                
                if st.button('Create Alert', type="primary"):
                    with st.spinner("Creating alert..."):
                        tweet_text = st.session_state.current_tweet_text
                        
                        test_lat = st.session_state.test_tweet_lat
                        test_lon = st.session_state.test_tweet_lon
                        
                        import sqlite3
                        from datetime import datetime
                        
                        conn = sqlite3.connect('crisis_alerts.db')
                        cursor = conn.cursor()
                        
                        cursor.execute('''
                            INSERT INTO alerts (text, lat, lon, time, status)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (tweet_text, test_lat, test_lon, datetime.now().isoformat(), 'pending'))
                        
                        alert_id = cursor.lastrowid
                        conn.commit()
                        conn.close()
                        
                        st.success(f"Alert #{alert_id} created and added to dashboard.")
                        st.info(f"Alert location: {st.session_state.test_tweet_location_desc} (Lat: {test_lat:.6f}, Lon: {test_lon:.6f})")
                        st.info("Go to the Dashboard to review and confirm this alert.")
                        
                        print(f"Tweet alert created - ID: {alert_id}, Location: {test_lat}, {test_lon}")
                        
                        st.session_state.tweet_is_disaster = False
                        st.session_state.current_tweet_text = ""
                        time.sleep(2)
                        st.rerun()
            else:
                st.subheader("Analyze Tweet Content")
                user_input = st.text_area('Enter a tweet:', 
                                         placeholder="e.g., Massive flooding has cut off access to downtown...",
                                         height=100)
                
                if st.button('Analyze Tweet', type="primary"):
                    with st.spinner("Analyzing..."):
                        check_tweet(user_input, model, vectorizer)
                        st.rerun()
        else:
            st.error("Model not loaded. Please ensure model.pkl and vectorizer.pkl files are available in the application directory.")

        with st.expander("About the Model"):
            st.write("""
            This disaster prediction model is a Support Vector Classifier model trained on Twitter data to classify tweets as either:
            - Related to real disasters (earthquakes, floods, etc.)
            - Not related to actual disasters (metaphorical usage, etc.)
            
            The model helps our system filter relevant crisis information from social media.
            """)
            
            st.info("""
            **How to use this feature:**
            
            1. Enter a tweet text and click "Analyze Tweet"
            2. If classified as a disaster, specify location for the event
            3. Create an alert that will appear on the Dashboard
            4. On the Dashboard, you can review, edit and confirm the alert
            """)
    
    print("Dashboard page accessed")

elif page == "User Registration":
    st.title("Register for Crisis Alerts")
    
    if not st.session_state.location_selected:
        current_step = 1
    elif 'location_confirmed' not in st.session_state:
        current_step = 2
    else:
        current_step = 3
    
    steps = ["Choose Location", "Confirm & Set Radius", "Complete Registration"]
    st.progress(current_step/len(steps))
    
    cols = st.columns(len(steps))
    for i, step in enumerate(steps):
        with cols[i]:
            if i+1 < current_step:
                st.markdown(f"✅ **Step {i+1}:** {step}")
            elif i+1 == current_step:
                st.markdown(f"🔵 **Step {i+1}:** {step}")
            else:
                st.markdown(f"⚪ **Step {i+1}:** {step}")
    
    st.write("---")
    
    if current_step == 1:
        st.subheader("📍 Step 1: Choose Your Location")
        
        st.info("""
        We need your location to send you relevant crisis alerts.
        Alerts will only be sent when a crisis is detected within your specified radius.
        """)
        
        location_input_method = st.radio(
            "How would you like to specify your location?",
            ["Address", "Coordinates"],
            index=0,
            horizontal=True,
            help="Choose whether to enter an address or direct coordinates"
        )
        if location_input_method == "Address":
            address = st.text_input("Enter your address, city, or location", 
                                placeholder="e.g., 123 Main St, New York, NY 10001",
                                help="This will be converted to coordinates for crisis alerting")
            
            find_location_button = st.button("Find Location", type="primary", use_container_width=True)
            
            if find_location_button:
                if address:
                    with st.spinner("Finding your location..."):
                        lat, lon, formatted_address = geocode_address(address)
                        if lat and lon:
                            st.success(f"Found your location: {formatted_address}")
                        else:
                            st.error(st.session_state.geocoding_error or "Could not geocode that address. Please try again.")
                else:
                    st.warning("Please enter an address to geocode")
            
            if st.session_state.location_selected and st.session_state.geocoded_address:
                next_button = st.button("Next ->", type="primary", use_container_width=True)
                if next_button:
                    st.rerun()
            
        else:
            st.text("Enter your coordinates:")
            input_lat = st.number_input("Latitude", value=22.5726459, format="%.6f",
                                    help="Enter your latitude coordinate")
            input_lon = st.number_input("Longitude", value=88.3638953, format="%.6f",
                                    help="Enter your longitude coordinate")
            
            set_location_button = st.button("Set Location", type="primary", use_container_width=True)
            
            if set_location_button:
                st.session_state.selected_location = {"lat": input_lat, "lon": input_lon}
                st.session_state.location_selected = True
                st.session_state.geocoded_address = f"Custom location (Lat: {input_lat:.6f}, Lon: {input_lon:.6f})"
                st.success(f"Location set to coordinates: Lat {input_lat:.6f}, Lon {input_lon:.6f}")
                st.rerun()

    elif current_step == 2:
        st.subheader("🔍 Step 2: Confirm Location & Set Alert Radius")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("### Your Selected Location")
            st.markdown(f"**📍 Address:** {st.session_state.geocoded_address}")
            st.markdown(f"**🌐 Coordinates:** Lat: {st.session_state.selected_location['lat']:.6f}, Lon: {st.session_state.selected_location['lon']:.6f}")
            
            st.markdown("### Set Your Alert Radius")
            st.write("You'll receive alerts for crises within this distance from your location:")
            radius = st.slider("Radius (km)", 
                            min_value=1, max_value=100, value=10, step=1,
                            help="You'll receive alerts within this distance from your location")
            
            confirm_button = st.button("Confirm Location & Radius", type="primary", use_container_width=True)
            if confirm_button:
                st.session_state.location_confirmed = True
                st.session_state.selected_radius = radius
                st.success("Location and notification radius confirmed!")
                st.rerun()
                
        with col2:
            approx_degree_per_km = 0.01 / 1.11
            radius_in_degrees = radius * approx_degree_per_km
            
            theta = np.linspace(0, 2*np.pi, 100)
            circle_lat = st.session_state.selected_location['lat'] + radius_in_degrees * np.cos(theta)
            circle_lon = st.session_state.selected_location['lon'] + radius_in_degrees * np.sin(theta)
            
            circle_df = pd.DataFrame({
                'lat': np.append(circle_lat, st.session_state.selected_location['lat']),
                'lon': np.append(circle_lon, st.session_state.selected_location['lon'])
            })
            
            st.map(circle_df)
            st.caption(f"The red circle represents approximately {radius} km radius around your location")
    
    elif current_step == 3:
        st.subheader("📱 Step 3: Complete Your Registration")
        
        st.success(f"✅ Location confirmed! You will receive alerts within {st.session_state.selected_radius} km of your location.")
        
        with st.container():
            st.markdown("### Enter Your Contact Information")
            st.info("Your phone number will be used to send SMS alerts when a crisis is detected near your location.")
            
            registration_completed = False
            
            with st.form("complete_registration_form", clear_on_submit=False):
                phone_number = st.text_input("Phone Number", 
                                          placeholder="+12345678901",
                                          help="Please include your country code with + sign")
                
                submit_col1, submit_col2 = st.columns([1, 1])
                with submit_col1:
                    complete_button = st.form_submit_button("Complete Registration", type="primary", use_container_width=True)
                with submit_col2:
                    back_button = st.form_submit_button("← Back to Location", use_container_width=True)
                
                if complete_button:
                    if not phone_number:
                        st.error("Please provide a phone number.")
                    elif not phone_number.startswith('+'):
                        st.error("Phone number must include country code (e.g., +1).")
                    else:
                        lat = st.session_state.selected_location["lat"]
                        lon = st.session_state.selected_location["lon"]
                        radius = st.session_state.selected_radius
                        
                        print(f"Registration: {phone_number}, location: ({lat}, {lon}), radius: {radius}")
                        
                        success = register_user(phone_number, lat, lon, radius)
                        if success:
                            st.success("🎉 Registration successful! You will now receive alerts for crises within your specified radius.")
                            registration_completed = True
                        else:
                            st.error("This phone number is already registered. Please use a different number.")
                
                if back_button:
                    if 'location_confirmed' in st.session_state:
                        del st.session_state.location_confirmed
                    st.rerun()

            if registration_completed:
                st.markdown("### What's Next?")
                st.markdown("- We'll monitor for crises in your area")
                st.markdown("- You'll receive SMS alerts when a crisis is confirmed near your location")
                st.markdown("- Stay safe and be prepared!")
                
                if st.button("Register Another Number"):
                    if 'location_confirmed' in st.session_state:
                        del st.session_state.location_confirmed
                        del st.session_state.selected_radius
                    st.session_state.location_selected = False
                    st.rerun()
    
    print("User Registration page accessed")

# Run the app
if __name__ == "__main__":
    print("Main application started")