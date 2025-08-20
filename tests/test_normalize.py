"""Tests for normalization utilities."""

import pytest
from civiphrases.normalize import (
    normalize_whitespace, 
    unify_quotes, 
    chunk_long_prompt,
    normalize_prompt,
    create_prompt_worklist,
    filter_empty_prompts
)


def test_normalize_whitespace():
    """Test whitespace normalization."""
    assert normalize_whitespace("  hello   world  ") == "hello world"
    assert normalize_whitespace("line1\n\nline2\t\ttab") == "line1 line2 tab"
    assert normalize_whitespace("") == ""
    assert normalize_whitespace("   ") == ""


def test_unify_quotes():
    """Test quote unification."""
    assert unify_quotes(""hello"") == '"hello"'
    assert unify_quotes("'hello'") == "'hello'"
    assert unify_quotes("") == ""


def test_chunk_long_prompt():
    """Test prompt chunking."""
    short_prompt = "short prompt"
    assert chunk_long_prompt(short_prompt, 100) == [short_prompt]
    
    long_prompt = "a, b, c, " * 100  # Very long prompt
    chunks = chunk_long_prompt(long_prompt, 50)
    assert len(chunks) > 1
    assert all(len(chunk) <= 50 or "," not in chunk for chunk in chunks)


def test_normalize_prompt():
    """Test complete prompt normalization."""
    messy_prompt = "  hello,,, world...   beautiful,  scene  "
    normalized = normalize_prompt(messy_prompt)
    assert normalized == "hello, world. beautiful, scene"


def test_create_prompt_worklist():
    """Test worklist creation."""
    items = [
        {
            "item_id": "test1",
            "positive": "beautiful landscape, sunset",
            "negative": "blurry, low quality"
        },
        {
            "item_id": "test2", 
            "positive": "",
            "negative": "ugly"
        }
    ]
    
    worklist = create_prompt_worklist(items)
    
    # Should have 3 entries: 1 positive from test1, 1 negative from test1, 1 negative from test2
    assert len(worklist) == 3
    
    pos_entries = [w for w in worklist if w["polarity"] == "pos"]
    neg_entries = [w for w in worklist if w["polarity"] == "neg"]
    
    assert len(pos_entries) == 1
    assert len(neg_entries) == 2


def test_filter_empty_prompts():
    """Test filtering of empty prompts."""
    worklist = [
        {"text": "good prompt", "polarity": "pos", "item_id": "1"},
        {"text": "   ", "polarity": "pos", "item_id": "2"},  # Empty
        {"text": ",,, ...", "polarity": "neg", "item_id": "3"},  # Just punctuation
        {"text": "another good prompt", "polarity": "neg", "item_id": "4"},
    ]
    
    filtered = filter_empty_prompts(worklist)
    assert len(filtered) == 2
    assert filtered[0]["text"] == "good prompt"
    assert filtered[1]["text"] == "another good prompt"

