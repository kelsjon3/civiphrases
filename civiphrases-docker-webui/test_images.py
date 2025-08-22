#!/usr/bin/env python3
"""Test script for image functionality."""

import requests
import json

def test_get_images():
    """Test the /get_images endpoint."""
    try:
        response = requests.get('http://localhost:5000/get_images')
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_get_images()
