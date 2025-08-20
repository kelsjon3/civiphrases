"""Text normalization and preprocessing utilities."""

import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text while preserving original casing."""
    if not text:
        return ""
    
    # Collapse multiple spaces/tabs/newlines into single spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def unify_quotes(text: str) -> str:
    """Unify different quote types to standard quotes."""
    if not text:
        return ""
    
    # Replace smart quotes with regular quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    
    return text


def chunk_long_prompt(text: str, max_length: int = 4000) -> List[str]:
    """
    Chunk very long prompts at natural boundaries (commas, semicolons).
    
    Args:
        text: The prompt text to chunk
        max_length: Maximum length per chunk
        
    Returns:
        List of text chunks
    """
    if not text or len(text) <= max_length:
        return [text] if text else []
    
    chunks = []
    current_chunk = ""
    
    # Split on commas and semicolons first
    parts = re.split(r'([,;])', text)
    
    for i, part in enumerate(parts):
        # If adding this part would exceed max length, save current chunk
        if current_chunk and len(current_chunk + part) > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = part
        else:
            current_chunk += part
    
    # Add the last chunk if not empty
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # If we still have chunks that are too long, split them more aggressively
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_length:
            final_chunks.append(chunk)
        else:
            # Split on spaces as last resort
            words = chunk.split()
            current = ""
            for word in words:
                if current and len(current + " " + word) > max_length:
                    final_chunks.append(current.strip())
                    current = word
                else:
                    if current:
                        current += " " + word
                    else:
                        current = word
            if current.strip():
                final_chunks.append(current.strip())
    
    return [chunk for chunk in final_chunks if chunk.strip()]


def normalize_prompt(text: str, lang: str = "all") -> str:
    """
    Normalize a prompt text with basic cleanup.
    
    Args:
        text: Raw prompt text
        lang: Language setting (currently unused, for future expansion)
        
    Returns:
        Normalized prompt text
    """
    if not text:
        return ""
    
    # Basic normalization
    text = normalize_whitespace(text)
    text = unify_quotes(text)
    
    # Remove excessive punctuation
    text = re.sub(r'[,]{2,}', ',', text)  # Multiple commas
    text = re.sub(r'[.]{2,}', '.', text)  # Multiple periods
    
    # Clean up spacing around punctuation
    text = re.sub(r'\s*,\s*', ', ', text)
    text = re.sub(r'\s*;\s*', '; ', text)
    text = re.sub(r'\s*\.\s*', '. ', text)
    
    # Remove trailing punctuation at the end
    text = text.rstrip(' ,;.')
    
    return text


def create_prompt_worklist(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert fetched items into a normalized worklist for LLM processing.
    
    Args:
        items: List of fetched items from Civitai
        
    Returns:
        List of normalized prompt entries ready for LLM classification
    """
    worklist = []
    
    for item in items:
        item_id = item["item_id"]
        positive = item.get("positive", "")
        negative = item.get("negative", "")
        
        # Process positive prompts
        if positive:
            normalized = normalize_prompt(positive)
            if normalized:
                # Check if prompt needs chunking
                chunks = chunk_long_prompt(normalized)
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{item_id}_pos_{i}" if len(chunks) > 1 else f"{item_id}_pos"
                    worklist.append({
                        "text": chunk,
                        "polarity": "pos",
                        "item_id": item_id,
                        "chunk_id": chunk_id
                    })
        
        # Process negative prompts
        if negative:
            normalized = normalize_prompt(negative)
            if normalized:
                # Check if prompt needs chunking
                chunks = chunk_long_prompt(normalized)
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{item_id}_neg_{i}" if len(chunks) > 1 else f"{item_id}_neg"
                    worklist.append({
                        "text": chunk,
                        "polarity": "neg",
                        "item_id": item_id,
                        "chunk_id": chunk_id
                    })
    
    logger.info(f"Created worklist with {len(worklist)} prompt entries")
    return worklist


def filter_empty_prompts(worklist: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out empty or very short prompts from worklist."""
    filtered = []
    
    for entry in worklist:
        text = entry["text"].strip()
        # Keep prompts that have actual content (more than just punctuation)
        if text and len(text) > 2 and not re.match(r'^[,.\s;]*$', text):
            filtered.append(entry)
    
    removed = len(worklist) - len(filtered)
    if removed > 0:
        logger.info(f"Filtered out {removed} empty/short prompts")
    
    return filtered
