#!/usr/bin/env python3
"""Direct test of TGW API to see what's happening with the responses."""

import requests
import json

def test_tgw_direct():
    """Test TGW API directly to see the actual responses."""
    
    # TGW configuration
    tgw_url = "http://192.168.73.124:5001/v1"
    model_name = "meta-llama-3.1-8b-instruct-abliterated.Q8_0.gguf"
    
    # Test prompt (similar to what civiphrases would send)
    system_prompt = """You are a phrase classifier. Split Stable Diffusion prompts into phrases and classify each phrase.

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

    user_prompt = "masterpiece, best quality, very aesthetic, absurdres, newest, depth of field, (Dramatic Lighting:1.5), 8K, 1girl, 1boy, beruzen eyes"
    
    # Prepare the request
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 4000,
        "temperature": 0.1,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.1
    }
    
    headers = {
        "Authorization": "Bearer local",
        "Content-Type": "application/json"
    }
    
    print("🧪 Testing TGW API directly...")
    print(f"URL: {tgw_url}")
    print(f"Model: {model_name}")
    print(f"Prompt: {user_prompt}")
    print(f"Max tokens: {payload['max_tokens']}")
    print()
    
    try:
        print("📤 Sending request...")
        response = requests.post(
            f"{tgw_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=60
        )
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success response structure: {list(data.keys())}")
            
            if 'choices' in data and data['choices']:
                choice = data['choices'][0]
                if 'message' in choice and 'content' in choice['message']:
                    content = choice['message']['content']
                    print(f"📝 Response content length: {len(content)}")
                    print(f"📝 Response content:")
                    print("=" * 50)
                    print(content)
                    print("=" * 50)
                    
                    # Try to parse as JSON
                    try:
                        parsed = json.loads(content)
                        print(f"✅ JSON parsing successful!")
                        print(f"📊 Parsed structure: {json.dumps(parsed, indent=2)}")
                        
                        if 'phrases' in parsed:
                            print(f"🎯 Found {len(parsed['phrases'])} phrases")
                            for i, phrase in enumerate(parsed['phrases']):
                                print(f"  {i+1}. {phrase.get('text', 'N/A')} -> {phrase.get('category', 'N/A')}")
                        else:
                            print("❌ No 'phrases' key found in parsed JSON")
                            
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON parsing failed: {e}")
                        print("🔍 Looking for JSON patterns...")
                        
                        # Look for JSON-like content
                        if '{' in content and '}' in content:
                            json_start = content.find('{')
                            json_end = content.rfind('}') + 1
                            json_part = content[json_start:json_end]
                            print(f"🔍 Extracted JSON-like content (length: {len(json_part)}):")
                            print(json_part)
                        else:
                            print("❌ No JSON-like content found")
                else:
                    print("❌ Unexpected response structure")
                    print(f"Response: {json.dumps(data, indent=2)}")
            else:
                print("❌ No choices in response")
                print(f"Response: {json.dumps(data, indent=2)}")
        else:
            print(f"❌ Error response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_tgw_direct()
