"""Tests for LLM classification utilities."""

import json
import pytest
from civiphrases.classify import ClassificationResponse, LLMClassifier


def test_classification_response_validation():
    """Test validation of classification response JSON."""
    valid_response = {
        "results": [
            {
                "source_id": "test1",
                "polarity": "pos",
                "phrases": [
                    {"text": "beautiful woman", "category": "subjects"},
                    {"text": "oil painting", "category": "styles"}
                ]
            }
        ]
    }
    
    # Should validate successfully
    validated = ClassificationResponse(**valid_response)
    assert len(validated.results) == 1
    assert len(validated.results[0].phrases) == 2


def test_classification_response_invalid():
    """Test validation with invalid data."""
    invalid_response = {
        "results": [
            {
                "source_id": "test1",
                "polarity": "invalid_polarity",  # Invalid
                "phrases": []
            }
        ]
    }
    
    with pytest.raises(Exception):  # Should raise validation error
        ClassificationResponse(**invalid_response)


def test_force_negatives_category():
    """Test forcing negative phrases to correct category."""
    classifier = LLMClassifier()
    
    # Mock results with mislabeled negatives
    from civiphrases.classify import ClassificationResult, PhraseClassification
    
    results = [
        ClassificationResult(
            source_id="test1",
            polarity="neg",
            phrases=[
                PhraseClassification(text="blurry", category="modifiers"),  # Should be negatives
                PhraseClassification(text="extra fingers", category="subjects"),  # Should be negatives
                PhraseClassification(text="good phrase", category="subjects")  # Should stay
            ]
        )
    ]
    
    fixed_results = classifier._force_negatives_category(results)
    
    assert fixed_results[0].phrases[0].category == "negatives"  # blurry moved
    assert fixed_results[0].phrases[1].category == "negatives"  # extra fingers moved
    assert fixed_results[0].phrases[2].category == "subjects"   # good phrase stayed

