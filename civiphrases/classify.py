"""LLM-based phrase classification using Text Generation WebUI OpenAI-compatible API."""

import json
import logging
import re
import time
from typing import List, Dict, Any, Optional
import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from .config import config

logger = logging.getLogger(__name__)


# Pydantic models for validation
class PhraseClassification(BaseModel):
    text: str
    category: str


class ClassificationResponse(BaseModel):
    phrases: List[PhraseClassification]


class LLMClassifier:
    """Classifier that uses local LLM to categorize prompt phrases."""
    
    # Valid categories as specified in the project plan
    VALID_CATEGORIES = {
        "subjects", "styles", "aesthetics", "techniques", 
        "quality_boosters", "negatives", "modifiers"
    }
    
    # System prompt as specified in the project plan
    SYSTEM_PROMPT = """You are a phrase classifier. Split Stable Diffusion prompts into phrases and classify each phrase.

CRITICAL: Output ONLY valid JSON. No text before or after the JSON. No explanations.

Task:
1) Split the prompt into natural phrases (usually 2-6 words)
2) Classify each phrase into exactly one category:
   - subjects: people, creatures, objects, characters, props
   - styles: art movements, render engines, mediums, franchises
   - aesthetics: lighting, mood, colors, atmosphere
   - techniques: camera terms, composition, lens settings
   - quality_boosters: "masterpiece", "best quality", "highly detailed"
   - negatives: "blurry", "extra fingers", "bad anatomy"
   - modifiers: "intricate", "minimalist", "cute"

Output format (JSON ONLY):
{
  "phrases": [
    {"text": "a beautiful girl", "category": "subjects"},
    {"text": "with red hair", "category": "modifiers"},
    {"text": "walks slowly through", "category": "techniques"},
    {"text": "a dark forest", "category": "subjects"}
  ]
}

Rules:
- Output ONLY the JSON object above
- No text before "{" or after "}"
- No commentary, reasoning, or explanations
- No "Here is the output" or similar text
- Ensure the JSON is complete and properly closed"""
    
    def __init__(self):
        """Initialize the LLM classifier."""
        self.client = OpenAI(
            base_url=config.tgw_base_url,
            api_key=config.tgw_api_key,
            timeout=120.0  # 2 minute timeout to prevent hanging requests
        )
        
        # Test connection and get model info
        self.model_name = self._get_available_model()
        logger.info(f"Initialized LLM classifier with model: {self.model_name}")
    
    def _get_available_model(self) -> str:
        """Get the first available model from the API or use the specified model."""
        try:
            models = self.client.models.list()
            if models.data:
                # If a specific model is requested, try to use it
                if config.tgw_model_name:
                    # Look for the requested model
                    for model in models.data:
                        if model.id == config.tgw_model_name:
                            logger.info(f"Using requested model: {model.id}")
                            return model.id
                    
                    # If requested model not found, log warning and fall back to first available
                    logger.warning(f"Requested model '{config.tgw_model_name}' not found, using first available")
                
                # Use first available model (default behavior)
                model_name = models.data[0].id
                logger.info(f"Using model: {model_name}")
                return model_name
            else:
                logger.warning("No models available, using default")
                return "default"
        except Exception as e:
            logger.warning(f"Could not fetch models, using default: {e}")
            return "default"
    
    def _create_batch_payload(self, worklist_batch: List[Dict[str, Any]]) -> str:
        """Create the user message payload for a batch of prompts."""
        # For now, just use the first prompt in the batch
        # We can expand this later if needed
        if worklist_batch:
            return worklist_batch[0]["text"]
        return ""
    
    def _validate_and_fix_response(self, response_text: str) -> Optional[ClassificationResponse]:
        """Validate LLM response and attempt to fix common issues."""
        # Clean the response text to extract JSON
        logger.info("Attempting to extract JSON from response...")
        cleaned_text = self._extract_json_from_response(response_text)
        
        if not cleaned_text:
            logger.error("Could not extract JSON from response")
            logger.error(f"Response text: {response_text[:500]}...")
            return None
        else:
            logger.info(f"Successfully extracted JSON (length: {len(cleaned_text)})")
            logger.info(f"Extracted JSON: {cleaned_text}")
        
        try:
            # Try to parse the cleaned JSON
            response_data = json.loads(cleaned_text)
            
            # Validate with Pydantic
            validated = ClassificationResponse(**response_data)
            
            # Additional validation: check categories
            for phrase in validated.phrases:
                if phrase.category not in self.VALID_CATEGORIES:
                    logger.warning(f"Invalid category '{phrase.category}' for phrase '{phrase.text}', skipping phrase")
                    continue
            
            return validated
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error after cleaning: {e}")
            logger.error(f"Cleaned text: {cleaned_text[:500]}...")
            return None
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return None
    
    def _extract_json_from_response(self, response_text: str) -> Optional[str]:
        """Extract JSON from response text that may contain extra content."""
        
        # Remove common prefixes like "Here is the output in JSON format:"
        text = response_text.strip()
        
        # Look for JSON object patterns
        # Find the first { and try to parse from there
        json_start = text.find('{')
        if json_start == -1:
            logger.warning("No JSON object found in response")
            return None
        
        # Extract from the first { to the end
        json_text = text[json_start:]
        
        # First, try to find complete JSON by matching braces
        complete_json = self._find_complete_json(json_text)
        if complete_json:
            return complete_json
        
        # If no complete JSON found, try to fix truncation
        logger.warning("Could not find complete JSON, attempting to fix truncation...")
        
        # Try to complete the JSON structure
        fixed_json = self._fix_truncated_json(json_text)
        if fixed_json:
            return fixed_json
        
        logger.error("Could not extract or fix JSON from response")
        return None
    
    def _find_complete_json(self, json_text: str) -> Optional[str]:
        """Find complete JSON by matching braces."""
        brace_count = 0
        for i, char in enumerate(json_text):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    # Found complete JSON object
                    complete_json = json_text[:i+1]
                    
                    # Validate it's actually JSON
                    try:
                        json.loads(complete_json)
                        logger.debug("Successfully extracted complete JSON")
                        return complete_json
                    except json.JSONDecodeError:
                        logger.debug("Extracted text is not valid JSON, trying to fix...")
                        continue
        
        return None
    
    def _fix_truncated_json(self, json_text: str) -> Optional[str]:
        """Fix truncated JSON by completing incomplete phrases and structure."""
        # Find all complete phrases
        phrases_pattern = r'{"text":\s*"[^"]*",\s*"category":\s*"[^"]*"}'
        matches = list(re.finditer(phrases_pattern, json_text))
        
        if not matches:
            logger.debug("No complete phrases found to work with")
            return None
        
        # Get the last complete phrase position
        last_complete_end = matches[-1].end()
        
        # Extract everything up to the last complete phrase
        partial_json = json_text[:last_complete_end]
        
        # Try different completion strategies
        completion_strategies = [
            # Strategy 1: Simple array and object closure
            partial_json + '\n  ]\n}',
            # Strategy 2: Add closing brackets with proper formatting
            partial_json + '\n]}',
            # Strategy 3: Just close the array and object
            partial_json + ']}',
            # Strategy 4: Add a comma and close (in case last phrase was incomplete)
            partial_json + ',]}',
        ]
        
        for completed_json in completion_strategies:
            try:
                # Validate the completed JSON
                parsed = json.loads(completed_json)
                
                # Additional validation: ensure it has the expected structure
                if 'phrases' in parsed and isinstance(parsed['phrases'], list):
                    logger.debug(f"Successfully fixed truncated JSON with {len(parsed['phrases'])} phrases")
                    return completed_json
                    
            except json.JSONDecodeError:
                continue
        
        # If all strategies failed, try to salvage what we can
        logger.debug("All completion strategies failed, trying salvage approach...")
        
        # Look for the last complete phrase and try to close from there
        if matches:
            # Get the content up to the last complete phrase
            salvage_json = json_text[:last_complete_end]
            
            # Try to close it properly
            try:
                salvage_json += '\n]}'
                parsed = json.loads(salvage_json)
                if 'phrases' in parsed and isinstance(parsed['phrases'], list):
                    logger.debug(f"Successfully salvaged JSON with {len(parsed['phrases'])} phrases")
                    return salvage_json
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _extract_partial_phrases(self, response_text: str) -> List[Dict[str, Any]]:
        """Extract partial phrases from a failed response as a last resort."""
        
        phrases = []
        
        # Look for phrase patterns in the text
        phrase_pattern = r'{"text":\s*"([^"]*)",\s*"category":\s*"([^"]*)"}'
        matches = re.finditer(phrase_pattern, response_text)
        
        for match in matches:
            text = match.group(1).strip()
            category = match.group(2).strip()
            
            # Validate the category
            if category in self.VALID_CATEGORIES:
                phrases.append({
                    "text": text,
                    "category": category,
                    "polarity": "pos",
                    "source_id": "partial_extraction"
                })
                logger.debug(f"Extracted partial phrase: {text} -> {category}")
            else:
                logger.warning(f"Skipping phrase with invalid category: {text} -> {category}")
        
        return phrases
    
    def classify_batch(self, worklist_batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Classify a batch of prompts using the LLM.
        
        Args:
            worklist_batch: List of prompt entries to classify
            
        Returns:
            List of classified phrase dictionaries
        """
        if not worklist_batch:
            return []
        
        logger.debug(f"Classifying batch of {len(worklist_batch)} prompts")
        
        # Create the payload
        user_message = self._create_batch_payload(worklist_batch)
        
        # Prepare the messages
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # Make the API call
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=4000,  # Much higher limit to prevent truncation
                temperature=0.1,
                # TGW-specific parameters to improve response quality
                top_p=0.9,
                frequency_penalty=0.1,
                presence_penalty=0.1,
                timeout=120  # 2 minute timeout to prevent hanging
            )
            
            response_text = response.choices[0].message.content
            
            # Log the full response for debugging
            logger.info(f"Raw LLM response (length: {len(response_text)}): {response_text}")
            
            # Also log the first and last 200 characters to see truncation
            if len(response_text) > 400:
                logger.info(f"Response preview - First 200 chars: {response_text[:200]}")
                logger.info(f"Response preview - Last 200 chars: {response_text[-200:]}")
            else:
                logger.info(f"Full response: {response_text}")
            
            # Validate and parse the response
            validated_response = self._validate_and_fix_response(response_text)
            
            if validated_response:
                # Convert to list of phrase dictionaries
                phrases = []
                for phrase in validated_response.phrases:
                    phrases.append({
                        "text": phrase.text.strip(),
                        "category": phrase.category,
                        "polarity": "pos", # Default polarity
                        "source_id": worklist_batch[0]["item_id"] if worklist_batch else "N/A"
                    })
                
                logger.debug(f"Successfully classified {len(phrases)} phrases")
                return phrases
            else:
                logger.error("Failed to validate LLM response")
                
                # Fallback: try to extract partial phrases from the raw response
                logger.info("Attempting to extract partial phrases from failed response...")
                partial_phrases = self._extract_partial_phrases(response_text)
                
                if partial_phrases:
                    logger.info(f"Successfully extracted {len(partial_phrases)} partial phrases")
                    for phrase in partial_phrases:
                        logger.info(f"  - {phrase['text']} -> {phrase['category']}")
                    return partial_phrases
                else:
                    logger.error("No partial phrases could be extracted either")
                
                return []
                
        except Exception as e:
            logger.error(f"Error during LLM classification: {e}")
            logger.error(f"Exception type: {type(e)}")
            
            # Check for specific timeout-related errors
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                logger.error("LLM request timed out - this may indicate the model is hanging")
            elif "connection" in str(e).lower():
                logger.error("Connection error - check if TGW is responsive")
            
            return []
    
    def classify_worklist(
        self, 
        worklist: List[Dict[str, Any]], 
        batch_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Classify an entire worklist in batches.
        
        Args:
            worklist: Complete list of prompt entries
            batch_size: Number of prompts per batch
            
        Returns:
            List of all classified phrases
        """
        all_phrases = []
        total_batches = (len(worklist) + batch_size - 1) // batch_size
        
        logger.info(f"Classifying {len(worklist)} prompts in {total_batches} batches")
        
        for i in range(0, len(worklist), batch_size):
            batch = worklist[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            logger.info(f"Processing batch {batch_num}/{total_batches}")
            
            batch_phrases = self.classify_batch(batch)
            all_phrases.extend(batch_phrases)
            
            # Small delay between batches to be respectful to the API
            if i + batch_size < len(worklist):
                time.sleep(1)
        
        logger.info(f"Completed classification: {len(all_phrases)} total phrases")
        return all_phrases
