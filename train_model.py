import pandas as pd
import streamlit as st
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer

def train_model():
    # Load and prepare training data
    train_data = pd.read_csv('./tweets.csv')
    
    # Handle missing values
    imputer = SimpleImputer(strategy='constant', fill_value='')
    train_data = pd.DataFrame(imputer.fit_transform(train_data), columns=train_data.columns)
    
    # Feature extraction
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(train_data['text'])
    Y = train_data['target']
    
    # Train-test split
    X_train, X_test, Y_train, Y_test = train_test_split(
        X, Y, test_size=0.2, random_state=42
    )
    
    # Model training
    clf = SVC()
    clf.fit(X_train, Y_train.astype('int'))
    
    # Evaluate model
    accuracy = clf.score(X_test, Y_test.astype('int'))
    print(f"Model Accuracy: {accuracy:.4f}")
    
    print("Saving Model")
    pickle.dump(clf, open('model.pkl', 'wb'))
    pickle.dump(vectorizer, open('vectorizer.pkl', 'wb'))
    print("Model saved successfully!")

if "__name__" == "__main__":
    train_model()