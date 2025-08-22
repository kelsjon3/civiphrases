"""Civitai API client for fetching prompts and metadata."""

import hashlib
import json
import logging
import re
import time
from typing import Dict, List, Optional, Generator, Any
from urllib.parse import urlparse, parse_qs
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import config

logger = logging.getLogger(__name__)


class CivitaiClient:
    """Client for interacting with the Civitai API."""
    
    def __init__(self):
        self.session = requests.Session()
        
        # Set up retry strategy
        retry_strategy = Retry(
            total=config.max_retries,
            backoff_factor=config.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set headers
        headers = {
            "User-Agent": "civiphrases/0.1.0",
            "Accept": "application/json",
        }
        
        if config.civitai_api_key:
            headers["Authorization"] = f"Bearer {config.civitai_api_key}"
        
        self.session.headers.update(headers)
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a request to the Civitai API with rate limiting and error handling."""
        try:
            time.sleep(config.rate_limit_delay)
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def _extract_collection_id(self, collection_input: str) -> Optional[str]:
        """Extract collection ID from URL or return as-is if it's already an ID."""
        # If it's already just a number, return it
        if collection_input.isdigit():
            return collection_input
        
        # Try to extract from URL
        if "civitai.com/collections/" in collection_input:
            match = re.search(r"/collections/(\d+)", collection_input)
            if match:
                return match.group(1)
        
        logger.error(f"Could not extract collection ID from: {collection_input}")
        return None
    
    def _extract_prompt_data(self, item: Dict) -> Dict[str, Any]:
        """Extract prompt data from a Civitai API response item."""
        # Generate a stable item ID
        item_id = str(item.get("id", ""))
        if not item_id:
            item_id = hashlib.md5(str(item).encode()).hexdigest()[:16]
        
        # Extract prompts from meta field
        meta = item.get("meta", {})
        positive = ""
        negative = ""
        
        # Try different field names for prompts
        if isinstance(meta, dict):
            positive = meta.get("prompt", "") or meta.get("positivePrompt", "")
            negative = meta.get("negativePrompt", "") or meta.get("negative", "")
        
        # If meta is a string, try to parse it as JSON
        elif isinstance(meta, str):
            try:
                meta_dict = json.loads(meta)
                positive = meta_dict.get("prompt", "") or meta_dict.get("positivePrompt", "")
                negative = meta_dict.get("negativePrompt", "") or meta_dict.get("negative", "")
            except json.JSONDecodeError:
                pass
        
        # Extract other metadata
        created = item.get("createdAt", item.get("publishedAt", ""))
        
        # Build metadata dict
        metadata = {
            "model": meta.get("Model") or meta.get("model", "") if isinstance(meta, dict) else "",
            "sampler": meta.get("Sampler") or meta.get("sampler", "") if isinstance(meta, dict) else "",
            "seed": str(meta.get("Seed") or meta.get("seed", "")) if isinstance(meta, dict) else "",
        }
        
        # Add other available metadata
        if isinstance(meta, dict):
            for key in ["steps", "cfgScale", "size", "clipSkip"]:
                if key in meta:
                    metadata[key] = meta[key]
        
        # Extract image data for display
        image_data = {}
        if "url" in item:
            image_data["url"] = item["url"]
        elif "data" in item and isinstance(item["data"], dict) and "url" in item["data"]:
            image_data["url"] = item["data"]["url"]
        
        # Extract title/name
        image_data["title"] = item.get("name", item.get("title", ""))
        
        # Extract model information
        model_name = ""
        if isinstance(meta, dict):
            model_name = meta.get("Model") or meta.get("model", "")
        image_data["model"] = model_name
        
        # Extract creation date
        image_data["created"] = created
        
        return {
            "item_id": item_id,
            "positive": str(positive).strip(),
            "negative": str(negative).strip(),
            "created": created,
            "meta": metadata,
            "image_data": image_data,  # New field for image display
        }
    
    def fetch_user_images(
        self, 
        username: str, 
        max_items: int = 200, 
        include_nsfw: bool = False
    ) -> Generator[Dict[str, Any], None, None]:
        """Fetch images from a specific user."""
        logger.info(f"Fetching images for user: {username}")
        
        url = f"{config.civitai_base_url}/images"
        params = {
            "username": username,
            "limit": min(100, max_items),  # API max is usually 100
            "sort": "Most Reactions",
            "period": "AllTime",
        }
        
        if not include_nsfw:
            params["nsfw"] = "false"
        
        fetched = 0
        page = 1
        
        while fetched < max_items:
            current_params = params.copy()
            current_params["page"] = page
            
            logger.debug(f"Fetching page {page} for user {username}")
            
            data = self._make_request(url, current_params)
            if not data or "items" not in data:
                logger.warning(f"No data returned for page {page}")
                break
            
            items = data["items"]
            if not items:
                logger.info("No more items available")
                break
            
            for item in items:
                if fetched >= max_items:
                    break
                
                # Skip NSFW if not included
                if not include_nsfw and item.get("nsfw"):
                    continue
                
                prompt_data = self._extract_prompt_data(item)
                prompt_data["source"] = {"type": "user", "identifier": username}
                
                yield prompt_data
                fetched += 1
            
            page += 1
            
            # If we got fewer items than requested, we've reached the end
            if len(items) < params["limit"]:
                break
        
        logger.info(f"Fetched {fetched} items for user {username}")
    
    def fetch_collection_images(
        self, 
        collection_input: str, 
        max_items: int = 200, 
        include_nsfw: bool = False
    ) -> Generator[Dict[str, Any], None, None]:
        """Fetch images from a specific collection."""
        collection_id = self._extract_collection_id(collection_input)
        if not collection_id:
            return
        
        logger.info(f"Fetching images for collection: {collection_id}")
        
        url = f"{config.civitai_base_url}/collections/{collection_id}"
        
        # First, get collection details
        collection_data = self._make_request(url)
        if not collection_data:
            logger.error(f"Could not fetch collection {collection_id}")
            return
        
        # Now fetch images from the collection
        images_url = f"{config.civitai_base_url}/collections/{collection_id}/items"
        params = {
            "limit": min(100, max_items),
            "type": "image",
        }
        
        fetched = 0
        page = 1
        
        while fetched < max_items:
            current_params = params.copy()
            current_params["page"] = page
            
            logger.debug(f"Fetching page {page} for collection {collection_id}")
            
            data = self._make_request(images_url, current_params)
            if not data or "items" not in data:
                logger.warning(f"No data returned for page {page}")
                break
            
            items = data["items"]
            if not items:
                logger.info("No more items available")
                break
            
            for item in items:
                if fetched >= max_items:
                    break
                
                # Extract the actual image data
                image_data = item.get("data", item)
                
                # Skip NSFW if not included
                if not include_nsfw and image_data.get("nsfw"):
                    continue
                
                prompt_data = self._extract_prompt_data(image_data)
                prompt_data["source"] = {"type": "collection", "identifier": collection_id}
                
                yield prompt_data
                fetched += 1
            
            page += 1
            
            # If we got fewer items than requested, we've reached the end
            if len(items) < params["limit"]:
                break
        
        logger.info(f"Fetched {fetched} items for collection {collection_id}")


def calculate_item_checksum(positive: str, negative: str) -> str:
    """Calculate checksum for prompt content to detect changes."""
    content = f"{positive}|{negative}"
    return hashlib.md5(content.encode()).hexdigest()


def load_existing_items(items_file: str) -> Dict[str, Dict]:
    """Load existing items from JSONL file."""
    items = {}
    if not os.path.exists(items_file):
        return items
    
    try:
        with open(items_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    items[item["item_id"]] = item
    except (json.JSONDecodeError, KeyError, IOError) as e:
        logger.error(f"Error loading existing items: {e}")
    
    return items


def save_items_incrementally(items_file: str, new_items: List[Dict]):
    """Save new items to JSONL file incrementally."""
    try:
        with open(items_file, 'a', encoding='utf-8') as f:
            for item in new_items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        # Set proper ownership after writing
        try:
            # Use the actual UID/GID numbers for nobody:users (99:100)
            uid = 99
            gid = 100
            os.chown(items_file, uid, gid)
        except OSError:
            # Log but don't fail if we can't set ownership
            pass
            
    except IOError as e:
        logger.error(f"Error saving items: {e}")


# Fix missing import
import os
