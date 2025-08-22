#!/usr/bin/env python3
"""Image capture module for civiphrases web UI."""

import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ImageCapture:
    """Captures and formats image data from civiphrases."""
    
    def __init__(self):
        self.images = []
        self.source = None
    
    def capture_from_civitai_response(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Capture image data from a Civitai API response item."""
        image_data = {}
        
        # Extract image URL
        if "url" in item:
            image_data["url"] = item["url"]
        elif "data" in item and isinstance(item["data"], dict) and "url" in item["data"]:
            image_data["url"] = item["data"]["url"]
        
        # Extract title/name
        image_data["title"] = item.get("name", item.get("title", "Untitled"))
        
        # Extract model information
        meta = item.get("meta", {})
        model_name = ""
        if isinstance(meta, dict):
            model_name = meta.get("Model") or meta.get("model", "")
        image_data["model"] = model_name
        
        # Extract creation date
        created = item.get("createdAt", item.get("publishedAt", ""))
        image_data["created"] = created
        
        # Extract item ID
        image_data["id"] = str(item.get("id", ""))
        
        return image_data
    
    def format_for_webui(self, images: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
        """Format image data for web UI display."""
        formatted_images = []
        
        for img in images:
            if img.get("url"):  # Only include images with valid URLs
                formatted_images.append({
                    "id": img.get("id", ""),
                    "url": img["url"],
                    "title": img.get("title", "Untitled"),
                    "model": img.get("model", "Unknown Model"),
                    "created": img.get("created", ""),
                    "source": source
                })
        
        return formatted_images
    
    def log_image_data(self, images: List[Dict[str, Any]], source: str):
        """Log image data in a format that can be captured by the web UI."""
        if images:
            logger.info(f"CAPTURED_IMAGES: {json.dumps({'images': images, 'source': source})}")
            logger.info(f"Total images captured: {len(images)} from {source}")

def capture_images_from_civitai_items(items: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    """Utility function to capture images from civitai items."""
    capture = ImageCapture()
    captured_images = []
    
    for item in items:
        image_data = capture.capture_from_civitai_response(item)
        if image_data.get("url"):
            captured_images.append(image_data)
    
    # Log the captured data
    capture.log_image_data(captured_images, source)
    
    return captured_images
