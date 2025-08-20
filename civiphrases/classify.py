"""LLM-based phrase classification using Text Generation WebUI OpenAI-compatible API."""

import json
import logging
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


class ClassificationResult(BaseModel):
    source_id: str
    polarity: str
    phrases: List[PhraseClassification]


class ClassificationResponse(BaseModel):
    results: List[ClassificationResult]


class LLMClassifier:
    """Classifier that uses local LLM to categorize prompt phrases."""
    
    # Valid categories as specified in the project plan
    VALID_CATEGORIES = {
        "subjects", "styles", "aesthetics", "techniques", 
        "quality_boosters", "negatives", "modifiers"
    }
    
    # System prompt as specified in the project plan
    SYSTEM_PROMPT = """You are a classifier that takes Stable Diffusion prompts and prepares them for use in ComfyUI's Dynamic Prompts.

Task:
1) Input will be one or more prompts, often long and comma-separated.
2) Split each prompt into short, distinct phrases. (A phrase is usually 1–4 words; do not merge multiple ideas.)
3) For each phrase, assign exactly one category from this set:
   - subjects (people, creatures, objects, characters, props)
   - styles (art movements, render engines, mediums, franchises/brands, "in the style of")
   - aesthetics (lighting, mood, colors, atmosphere)
   - techniques (camera terms, composition, lens settings, 3D/photography jargon)
   - quality_boosters (e.g., "masterpiece", "best quality", "highly detailed")
   - negatives (undesirable features like "blurry", "extra fingers", "bad anatomy")
   - modifiers (generic adjectives like "intricate", "minimalist", "cute")
4) Output strictly as JSON with this schema:

{
  "results": [
    {
      "source_id": "string",              // item_id from the caller
      "polarity": "pos" | "neg",          // prompt polarity
      "phrases": [
        { "text": "string", "category": "subjects" },
        ...
      ]
    },
    ...
  ]
}

Rules:
- No commentary; JSON only.
- Do not invent phrases; only split what is present.
- Normalize spacing; do not lowercase the phrase text.
- Keep JSON valid and parseable."""
    
    def __init__(self):
        """Initialize the LLM classifier."""
        self.client = OpenAI(
            base_url=config.tgw_base_url,
            api_key=config.tgw_api_key
        )
        
        # Test connection and get model info
        self.model_name = self._get_available_model()
        logger.info(f"Initialized LLM classifier with model: {self.model_name}")
    
    def _get_available_model(self) -> str:
        """Get the first available model from the API."""
        try:
            models = self.client.models.list()
            if models.data:
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
        batch_data = {
            "batch": []
        }
        
        for entry in worklist_batch:
            batch_data["batch"].append({
                "source_id": entry["item_id"],
                "polarity": entry["polarity"],
                "prompt": entry["text"]
            })
        
        return json.dumps(batch_data, ensure_ascii=False)
    
    def _validate_and_fix_response(self, response_text: str) -> Optional[ClassificationResponse]:
        """Validate LLM response and attempt to fix common issues."""
        try:
            # Try to parse as JSON first
            response_data = json.loads(response_text)
            
            # Validate with Pydantic
            validated = ClassificationResponse(**response_data)
            
            # Additional validation: check categories
            for result in validated.results:
                for phrase in result.phrases:
                    if phrase.category not in self.VALID_CATEGORIES:
                        logger.warning(f"Invalid category '{phrase.category}' for phrase '{phrase.text}', skipping phrase")
                        continue
            
            return validated
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Response text: {response_text[:500]}...")
            return None
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return None
    
    def _force_negatives_category(self, results: List[ClassificationResult]) -> List[ClassificationResult]:
        """Force obvious negative phrases back to 'negatives' category if LLM mislabeled them."""
        
        # Common negative phrases that should always be in negatives category
        negative_indicators = {
            "blurry", "blur", "out of focus", "unfocused",
            "extra fingers", "extra limbs", "extra arms", "extra legs",
            "bad anatomy", "bad hands", "bad face", "deformed",
            "ugly", "disgusting", "gross", "horrific",
            "low quality", "low res", "low resolution", "pixelated",
            "artifacts", "compression", "jpeg artifacts",
            "worst quality", "bad quality", "poor quality",
            "distorted", "malformed", "mutated", "disfigured",
            "cropped", "cut off", "partial", "incomplete",
            "duplicate", "doubled", "multiple", "cloned",
            "watermark", "signature", "text", "logo", "copyright",
            "nsfw", "nude", "naked", "explicit"
        }
        
        fixed_results = []
        
        for result in results:
            fixed_phrases = []
            
            for phrase in result.phrases:
                phrase_lower = phrase.text.lower()
                
                # If this is from a negative prompt or contains negative indicators, force to negatives
                if (result.polarity == "neg" or 
                    any(neg_word in phrase_lower for neg_word in negative_indicators)):
                    
                    if phrase.category != "negatives":
                        logger.debug(f"Forcing phrase '{phrase.text}' to 'negatives' category")
                        phrase.category = "negatives"
                
                fixed_phrases.append(phrase)
            
            result.phrases = fixed_phrases
            fixed_results.append(result)
        
        return fixed_results
    
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
        
        # Prepare messages
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        max_attempts = 2
        
        for attempt in range(max_attempts):
            try:
                # Make the API call
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.1,  # Low temperature for consistent classification
                    max_tokens=4000,  # Should be enough for most batches
                    timeout=60
                )
                
                response_text = response.choices[0].message.content
                logger.debug(f"Raw LLM response: {response_text[:200]}...")
                
                # Validate the response
                validated_response = self._validate_and_fix_response(response_text)
                
                if validated_response:
                    # Apply negative phrase correction
                    fixed_results = self._force_negatives_category(validated_response.results)
                    
                    # Convert to list of phrase dictionaries
                    phrases = []
                    for result in fixed_results:
                        for phrase in result.phrases:
                            phrases.append({
                                "text": phrase.text.strip(),
                                "category": phrase.category,
                                "polarity": result.polarity,
                                "source_id": result.source_id
                            })
                    
                    logger.debug(f"Successfully classified {len(phrases)} phrases")
                    return phrases
                
                else:
                    if attempt < max_attempts - 1:
                        logger.warning(f"Invalid response on attempt {attempt + 1}, retrying with stricter instruction")
                        # Add stricter instruction for retry
                        messages.append({
                            "role": "assistant", 
                            "content": response_text
                        })
                        messages.append({
                            "role": "user", 
                            "content": "Return only valid JSON as specified."
                        })
                    else:
                        logger.error("Failed to get valid response after all attempts")
                        return []
                
            except Exception as e:
                logger.error(f"Error during LLM classification on attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    return []
        
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
