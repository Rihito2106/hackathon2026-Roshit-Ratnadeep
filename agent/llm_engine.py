import json
import requests
import re

# Default Ollama local port
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

def query_mistral(prompt: str) -> dict:
    """
    Sends a prompt to local Mistral and strictly enforces a JSON response.
    Includes a Regex fallback parser to prevent crashes.
    """
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "format": "json",  # Forces Ollama to output JSON
        "stream": False,
        "options": {
            "temperature": 0.1, # Keep it highly deterministic and logical
            "num_ctx": 4096     # Ensure enough context window for our KB and tools
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        response.raise_for_status()
        result_text = response.json().get("response", "")
        
        # 🛡️ THE ROBUST PARSER (Anti-Break System)
        try:
            # First, try to parse it cleanly
            parsed_data = json.loads(result_text)
            return validate_schema(parsed_data)
        except json.JSONDecodeError:
            # Fallback: If Mistral added text outside the JSON, hunt for the brackets
            match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if match:
                try:
                    parsed_data = json.loads(match.group(0))
                    return validate_schema(parsed_data)
                except Exception:
                    pass
            
            # If all parsing fails, trigger a safe escalation
            return safe_escalation("LLM output was unparseable garbage.")
            
    except Exception as e:
        print(f"🚨 API / Connection Error: {str(e)}")
        return safe_escalation(f"Ollama connection failed: {str(e)}")


def validate_schema(data: dict) -> dict:
    """Ensures the LLM returned our exact required keys."""
    required_keys = ["thought", "tool", "input", "confidence"]
    
    # If any key is missing, add a default so the loop doesn't throw a KeyError
    for key in required_keys:
        if key not in data:
            if key == "input":
                data[key] = {}
            elif key == "confidence":
                data[key] = 0.0
            else:
                data[key] = "MISSING"
                
    return data

def safe_escalation(reason: str) -> dict:
    """Failsafe dictionary if the brain completely breaks."""
    return {
        "thought": f"SYSTEM FAILURE: {reason}. Forcing immediate escalation.",
        "tool": "escalate",
        "input": {
            "ticket_id": "UNKNOWN", 
            "summary": "Agent logic crashed. Manual review required.", 
            "priority": "high"
        },
        "confidence": 0.0
    }

if __name__ == "__main__":
    # Test if your local Mistral is awake and responding correctly
    print("🧠 Testing Mistral Connection...")
    test_prompt = """
    You are an AI. Reply with ONLY valid JSON matching this schema:
    {
        "thought": "your reasoning",
        "tool": "get_customer",
        "input": {"email": "test@example.com"},
        "confidence": 0.99
    }
    """
    
    response = query_mistral(test_prompt)
    print("\n✅ Successfully Parsed Output:")
    print(json.dumps(response, indent=2))