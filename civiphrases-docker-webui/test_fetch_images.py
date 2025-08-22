#!/usr/bin/env python3
"""Test script for the new fetch_civitai_images endpoint."""

import requests
import json

def test_fetch_images():
    """Test the new fetch_civitai_images endpoint."""
    url = 'http://localhost:5000/fetch_civitai_images'
    
    # Test data - replace with your actual values
    test_data = {
        'username': 'JANO_16',  # Use the same username from your logs
        'collection_url': '',
        'max_items': 10,
        'include_nsfw': True,
        'civitai_api_key': 'ae911fe7d9d7a17fb36d741211eb4667'  # Your API key from logs
    }
    
    try:
        print("Testing fetch_civitai_images endpoint...")
        print(f"URL: {url}")
        print(f"Data: {json.dumps(test_data, indent=2)}")
        
        response = requests.post(url, json=test_data, timeout=30)
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Success Response:")
            print(json.dumps(data, indent=2))
            
            if data.get('success') and data.get('images'):
                print(f"\n📊 Summary:")
                print(f"  - Total images: {len(data['images'])}")
                print(f"  - Source: {data.get('source')}")
                
                # Show first image details
                if data['images']:
                    first_image = data['images'][0]
                    print(f"\n🖼️  First Image:")
                    print(f"  - ID: {first_image.get('id')}")
                    print(f"  - Title: {first_image.get('title')}")
                    print(f"  - Model: {first_image.get('model')}")
                    print(f"  - URL: {first_image.get('url')}")
                    print(f"  - Positive prompt length: {len(first_image.get('positive_prompt', ''))}")
                    print(f"  - Negative prompt length: {len(first_image.get('negative_prompt', ''))}")
        else:
            print(f"\n❌ Error Response:")
            print(f"Status: {response.status_code}")
            print(f"Text: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_fetch_images()
