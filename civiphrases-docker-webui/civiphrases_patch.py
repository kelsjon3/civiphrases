#!/usr/bin/env python3
"""
Patch for civiphrases module to enable image capture for web UI.

This patch modifies the civiphrases module to capture and log image data
that can be displayed in the web UI.
"""

import os
import sys
import json
import logging

# Add the civiphrases directory to the path
civiphrases_path = os.path.join(os.path.dirname(__file__), '..', 'civiphrases')
sys.path.insert(0, civiphrases_path)

from civitai import CivitaiClient

# Monkey patch the CivitaiClient to capture image data
original_fetch_user_images = CivitaiClient.fetch_user_images
original_fetch_collection_images = CivitaiClient.fetch_collection_images

def patched_fetch_user_images(self, username, max_items=200, include_nsfw=False):
    """Patched version that captures image data."""
    logger = logging.getLogger(__name__)
    
    # Call the original method
    items_generator = original_fetch_user_images(self, username, max_items, include_nsfw)
    
    # Collect items and capture image data
    items = []
    for item in items_generator:
        items.append(item)
        yield item
    
    # Log captured image data
    if items:
        captured_images = []
        for item in items:
            image_data = {
                'id': str(item.get('item_id', '')),
                'url': item.get('image_data', {}).get('url', ''),
                'title': item.get('image_data', {}).get('title', 'Untitled'),
                'model': item.get('image_data', {}).get('model', 'Unknown Model'),
                'created': item.get('image_data', {}).get('created', ''),
            }
            if image_data['url']:
                captured_images.append(image_data)
        
        if captured_images:
            logger.info(f"CAPTURED_IMAGES: {json.dumps({'images': captured_images, 'source': f'user: {username}'})}")

def patched_fetch_collection_images(self, collection_input, max_items=200, include_nsfw=False):
    """Patched version that captures image data."""
    logger = logging.getLogger(__name__)
    
    # Call the original method
    items_generator = original_fetch_collection_images(self, collection_input, max_items, include_nsfw)
    
    # Collect items and capture image data
    items = []
    for item in items_generator:
        items.append(item)
        yield item
    
    # Log captured image data
    if items:
        captured_images = []
        for item in items:
            image_data = {
                'id': str(item.get('item_id', '')),
                'url': item.get('image_data', {}).get('url', ''),
                'title': item.get('image_data', {}).get('title', 'Untitled'),
                'model': item.get('image_data', {}).get('model', 'Unknown Model'),
                'created': item.get('image_data', {}).get('created', ''),
            }
            if image_data['url']:
                captured_images.append(image_data)
        
        if captured_images:
            logger.info(f"CAPTURED_IMAGES: {json.dumps({'images': captured_images, 'source': f'collection: {collection_input}'})}")

# Apply the patches
CivitaiClient.fetch_user_images = patched_fetch_user_images
CivitaiClient.fetch_collection_images = patched_fetch_collection_images

print("Applied civiphrases image capture patches successfully!")
