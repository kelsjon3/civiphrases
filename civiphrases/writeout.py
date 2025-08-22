"""Wildcard file writer and manifest generation for ComfyUI Dynamic Prompts."""

import os
import json
import logging
from collections import defaultdict, Counter
from datetime import datetime
from typing import List, Dict, Any

from .config import config

logger = logging.getLogger(__name__)


class WildcardWriter:
    """Handles writing wildcard files and maintaining state."""
    
    # Wildcard file mappings
    WILDCARD_FILES = {
        "subjects": "subjects.txt",
        "styles": "styles.txt", 
        "aesthetics": "aesthetics.txt",
        "techniques": "techniques.txt",
        "quality_boosters": "quality_boosters.txt",
        "negatives": "negatives.txt",
        "modifiers": "modifiers.txt",
    }
    
    def __init__(self):
        """Initialize the wildcard writer."""
        config.ensure_directories()
    
    def dedupe_phrases(self, phrases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate phrases by text (case-insensitive) while preserving original casing.
        
        Args:
            phrases: List of phrase dictionaries
            
        Returns:
            List of deduplicated phrase records
        """
        # Group phrases by normalized text (case-insensitive)
        phrase_groups = defaultdict(lambda: {
            "text": "",
            "category": "",
            "polarities": set(),
            "sources": set(),
            "count": 0
        })
        
        for phrase in phrases:
            text = phrase["text"].strip()
            if not text:
                continue
                
            text_key = text.lower()
            group = phrase_groups[text_key]
            
            # Use first occurrence's casing and category
            if not group["text"]:
                group["text"] = text
                group["category"] = phrase["category"]
            
            # Collect polarities and sources
            group["polarities"].add(phrase["polarity"])
            group["sources"].add(phrase["source_id"])
            group["count"] += 1
        
        # Convert to final format
        deduped = []
        for group in phrase_groups.values():
            if not group["text"]:
                continue
                
            # Determine final polarity
            polarities = group["polarities"]
            if len(polarities) == 1:
                polarity = list(polarities)[0]
            else:
                polarity = "mixed"
            
            deduped.append({
                "text": group["text"],
                "category": group["category"],
                "polarity": polarity,
                "sources": list(group["sources"]),
                "count": group["count"]
            })
        
        logger.info(f"Deduplicated {len(phrases)} phrases to {len(deduped)} unique phrases")
        return deduped
    
    def apply_quality_filter(self, phrases: List[Dict[str, Any]], remove_generic: bool = False) -> List[Dict[str, Any]]:
        """
        Apply optional filtering to remove very generic quality boosters.
        
        Args:
            phrases: List of phrase records
            remove_generic: Whether to remove generic quality boosters
            
        Returns:
            Filtered phrase list
        """
        if not remove_generic:
            return phrases
        
        # Generic quality boosters to potentially remove
        generic_banlist = {
            "masterpiece", "best quality", "high quality", "highest quality",
            "ultra high quality", "extremely detailed", "highly detailed",
            "perfect", "flawless", "stunning", "amazing", "incredible",
            "photorealistic", "hyperrealistic", "realistic"
        }
        
        filtered = []
        removed_count = 0
        
        for phrase in phrases:
            if (phrase["category"] == "quality_boosters" and 
                phrase["text"].lower() in generic_banlist):
                removed_count += 1
                continue
            filtered.append(phrase)
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} generic quality boosters")
        
        return filtered
    
    def save_phrases_state(self, phrases: List[Dict[str, Any]]) -> None:
        """Save deduplicated phrases to state file."""
        try:
            with open(config.phrases_file, 'w', encoding='utf-8') as f:
                for phrase in phrases:
                    f.write(json.dumps(phrase, ensure_ascii=False) + '\n')
            
            logger.info(f"Saved {len(phrases)} phrases to {config.phrases_file}")
        except IOError as e:
            logger.error(f"Error saving phrases state: {e}")
    
    def load_phrases_state(self) -> List[Dict[str, Any]]:
        """Load phrases from state file."""
        phrases = []
        if not os.path.exists(config.phrases_file):
            return phrases
        
        try:
            with open(config.phrases_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        phrases.append(json.loads(line))
            logger.info(f"Loaded {len(phrases)} phrases from state")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading phrases state: {e}")
        
        return phrases
    
    def write_wildcard_files(self, phrases: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Write wildcard files for each category.
        
        Args:
            phrases: List of deduplicated phrase records
            
        Returns:
            Dictionary with counts per category
        """
        logger.info("=== Starting write_wildcard_files ===")
        logger.info(f"Processing {len(phrases)} phrases")
        
        # Group phrases by category
        logger.info("Grouping phrases by category...")
        category_phrases = defaultdict(list)
        
        for phrase in phrases:
            category = phrase["category"]
            if category in self.WILDCARD_FILES:
                category_phrases[category].append(phrase["text"])
        
        logger.info(f"Grouped into {len(category_phrases)} categories")
        counts = {}
        
        # Write individual category files
        logger.info("Writing individual category files...")
        for category, filename in self.WILDCARD_FILES.items():
            logger.info(f"Writing {category} to {filename}...")
            file_path = os.path.join(config.wildcards_dir, filename)
            phrase_list = category_phrases[category]
            
            # Sort alphabetically, preserving original casing
            phrase_list.sort()
            
            try:
                logger.info(f"Opening {file_path} for writing...")
                with open(file_path, 'w', encoding='utf-8') as f:
                    for phrase in phrase_list:
                        f.write(phrase + '\n')
                
                logger.info(f"File written successfully")
                
                counts[category] = len(phrase_list)
                logger.info(f"Wrote {len(phrase_list)} phrases to {filename}")
                
            except IOError as e:
                logger.error(f"Error writing {filename}: {e}")
                counts[category] = 0
        
        # Write prompt_bank.txt (union of all non-negative phrases)
        logger.info("Writing prompt_bank.txt...")
        prompt_bank_phrases = []
        for phrase in phrases:
            if phrase["category"] != "negatives":
                prompt_bank_phrases.append(phrase["text"])
        
        prompt_bank_phrases.sort()
        prompt_bank_path = os.path.join(config.wildcards_dir, "prompt_bank.txt")
        
        try:
            logger.info(f"Opening {prompt_bank_path} for writing...")
            with open(prompt_bank_path, 'w', encoding='utf-8') as f:
                for phrase in prompt_bank_phrases:
                    f.write(phrase + '\n')
            
            logger.info("File written successfully")
            
            counts["prompt_bank"] = len(prompt_bank_phrases)
            logger.info(f"Wrote {len(prompt_bank_phrases)} phrases to prompt_bank.txt")
            
        except IOError as e:
            logger.error(f"Error writing prompt_bank.txt: {e}")
            counts["prompt_bank"] = 0
        
        logger.info("=== write_wildcard_files completed successfully ===")
        return counts
    
    def create_manifest(
        self, 
        source_info: Dict[str, Any],
        phrase_counts: Dict[str, int],
        items_fetched: int,
        items_skipped: int,
        model_name: str,
        config_used: Dict[str, Any]
    ) -> None:
        """
        Create manifest.json with run metadata.
        
        Args:
            source_info: Information about the data source (user/collection)
            phrase_counts: Counts by category
            items_fetched: Number of items successfully fetched
            items_skipped: Number of items skipped
            model_name: LLM model used for classification
            config_used: Configuration parameters used
        """
        manifest = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": source_info,
            "statistics": {
                "items_fetched": items_fetched,
                "items_skipped": items_skipped,
                "total_phrases": sum(phrase_counts.values()) - phrase_counts.get("prompt_bank", 0),
                "phrase_counts": phrase_counts
            },
            "model_info": {
                "name": model_name,
                "api_base": config_used.get("tgw_base_url", "")
            },
            "configuration": config_used,
            "version": "0.1.0"
        }
        
        try:
            with open(config.manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Created manifest at {config.manifest_file}")
        except IOError as e:
            logger.error(f"Error creating manifest: {e}")


def process_and_write_phrases(
    classified_phrases: List[Dict[str, Any]],
    source_info: Dict[str, Any],
    items_fetched: int,
    items_skipped: int,
    model_name: str,
    config_used: Dict[str, Any],
    remove_generic_quality: bool = False
) -> Dict[str, int]:
    """
    Process classified phrases and write all output files.
    
    Args:
        classified_phrases: Raw classified phrases from LLM
        source_info: Source information (user/collection)
        items_fetched: Number of items fetched
        items_skipped: Number of items skipped  
        model_name: LLM model name
        config_used: Configuration used
        remove_generic_quality: Whether to remove generic quality boosters
        
    Returns:
        Dictionary with phrase counts by category
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("=== Starting process_and_write_phrases ===")
    
    writer = WildcardWriter()
    
    # Deduplicate and process phrases
    logger.info("Deduplicating phrases...")
    deduped_phrases = writer.dedupe_phrases(classified_phrases)
    logger.info(f"Deduplication complete: {len(deduped_phrases)} phrases")
    
    # Apply quality filtering if requested
    logger.info("Applying quality filtering...")
    filtered_phrases = writer.apply_quality_filter(deduped_phrases, remove_generic_quality)
    logger.info(f"Quality filtering complete: {len(filtered_phrases)} phrases")
    
    # Save phrases state
    logger.info("Saving phrases state...")
    writer.save_phrases_state(filtered_phrases)
    logger.info("Phrases state saved")
    
    # Write wildcard files
    logger.info("Writing wildcard files...")
    phrase_counts = writer.write_wildcard_files(filtered_phrases)
    logger.info(f"Wildcard files written: {phrase_counts}")
    
    # Create manifest
    logger.info("Creating manifest...")
    writer.create_manifest(
        source_info=source_info,
        phrase_counts=phrase_counts,
        items_fetched=items_fetched,
        items_skipped=items_skipped,
        model_name=model_name,
        config_used=config_used
    )
    logger.info("Manifest created")
    
    logger.info("=== process_and_write_phrases completed successfully ===")
    return phrase_counts


def generate_dry_run_summary(phrases: List[Dict[str, Any]]) -> str:
    """
    Generate a summary for dry-run mode.
    
    Args:
        phrases: List of deduplicated phrase records
        
    Returns:
        Formatted summary string
    """
    import random
    
    # Count by category
    category_counts = Counter(phrase["category"] for phrase in phrases)
    
    # Group phrases by category
    category_phrases = defaultdict(list)
    for phrase in phrases:
        category_phrases[phrase["category"]].append(phrase["text"])
    
    summary_lines = [
        "\n=== DRY RUN SUMMARY ===\n",
        "Phrase counts by category:",
    ]
    
    for category in sorted(category_counts.keys()):
        count = category_counts[category]
        summary_lines.append(f"  {category}: {count}")
    
    summary_lines.append(f"\nTotal phrases: {len(phrases)}")
    
    # Show examples from each category
    summary_lines.append("\nExample phrases by category:")
    
    for category in sorted(category_phrases.keys()):
        phrases_in_category = category_phrases[category]
        examples = random.sample(phrases_in_category, min(5, len(phrases_in_category)))
        summary_lines.append(f"\n{category}:")
        for example in examples:
            summary_lines.append(f"  - {example}")
    
    # Generate sample prompts
    subjects = category_phrases.get("subjects", [])
    styles = category_phrases.get("styles", [])
    aesthetics = category_phrases.get("aesthetics", [])
    techniques = category_phrases.get("techniques", [])
    negatives = category_phrases.get("negatives", [])
    
    if subjects or styles or aesthetics or techniques:
        summary_lines.append("\nSample composite prompts:")
        
        # Positive prompt
        positive_parts = []
        if subjects:
            positive_parts.append(random.choice(subjects))
        if styles:
            positive_parts.append(random.choice(styles))
        if aesthetics:
            positive_parts.append(random.choice(aesthetics))
        if techniques:
            positive_parts.append(random.choice(techniques))
        
        if positive_parts:
            summary_lines.append(f"Positive: {', '.join(positive_parts)}")
        
        # Negative prompt
        if negatives:
            neg_sample = random.sample(negatives, min(3, len(negatives)))
            summary_lines.append(f"Negative: {', '.join(neg_sample)}")
    
    return "\n".join(summary_lines)
