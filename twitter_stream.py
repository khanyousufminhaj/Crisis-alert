import tweepy
import threading
import json
import time
import streamlit as st
from database import insert_alert
from utils import get_crisis_keywords

class CrisisStream(tweepy.StreamingClient):
    def __init__(self, bearer_token):
        super().__init__(bearer_token)
        self.crisis_keywords = get_crisis_keywords()
        
    def on_tweet(self, tweet):
        """Process incoming tweets with location data"""
        # Check if we have geo data
        if tweet.geo:
            text = tweet.text.lower()
            
            # Check if tweet contains crisis keywords
            if any(keyword in text for keyword in self.crisis_keywords):
                try:
                    # Extract coordinates if available
                    if tweet.geo.get('coordinates') and tweet.geo['coordinates'].get('coordinates'):
                        lon, lat = tweet.geo['coordinates']['coordinates']
                        # Store as a potential alert in the database
                        insert_alert(tweet.text, lat, lon)
                        print(f"Potential crisis detected: {tweet.text[:50]}... at {lat}, {lon}")
                except Exception as e:
                    print(f"Error processing tweet: {e}")
    
    def on_error(self, status):
        print(f"Error: {status}")
        if status == 420:  # Rate limit
            return False  # Stop the stream

    def on_connection_error(self):
        print("Twitter API connection error, reconnecting...")
        time.sleep(60)  # Wait before reconnecting


def start_twitter_stream(stop_event):
    """Start Twitter stream in a background thread"""
    try:
        # Get Twitter API credentials from Streamlit secrets
        bearer_token = st.secrets["twitter"]["bearer_token"]
        
        # Initialize the stream
        stream = CrisisStream(bearer_token)
        
        # Add rules for filtering tweets with crisis keywords and geo data
        # Delete existing rules
        rules = stream.get_rules()
        if rules.data:
            rule_ids = [rule.id for rule in rules.data]
            stream.delete_rules(rule_ids)
        
        # Add new rules
        keywords = " OR ".join(get_crisis_keywords())
        stream.add_rules(tweepy.StreamRule(f"({keywords}) has:geo"))
        
        # Start filtering
        stream.filter(tweet_fields=["geo"], expansions=["geo.place_id"])
        
        # Keep running until stop event is set
        while not stop_event.is_set():
            time.sleep(1)
        
        # Disconnect when stop event is set
        stream.disconnect()
        
    except Exception as e:
        print(f"Twitter streaming error: {e}")

def create_twitter_stream_thread():
    """Create and return a thread for Twitter streaming with a stop event"""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=start_twitter_stream, 
        args=(stop_event,),
        daemon=True
    )
    return thread, stop_event
