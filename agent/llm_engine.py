import json
import requests
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

VALID_TOOLS = {
    "get_order", "get_customer", "get_product", "search_knowledge_base",
    "check_refund_eligibility", "issue_refund", "send_reply", "escalate"
}

def query_mistral(prompt: str) -> dict:
    """
    Sends a prompt to local Mistral and strictly enforces a JSON response.
    Includes retry logic and a schema validator that catches bad tool names.
    """
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_predict": 350,  # FIX 3: Cap output — concise JSON only, no rambling
        }
    }

    # FIX 1: Retry loop with a long timeout
    # Under concurrent load, Ollama can take 60-90s per request on CPU.
    # We try up to 3 times before giving up and escalating.
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=120  # 2 minutes — generous for CPU inference under load
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")

            parsed = _parse_response(result_text)
            if parsed:
                return parsed

            # Parsing succeeded but schema was invalid — retry with tighter prompt
            if attempt < max_retries:
                print(f"  ⚠️  Schema invalid on attempt {attempt}, retrying...")
                payload["prompt"] = _repair_prompt(prompt, result_text)
                continue

        except requests.exceptions.Timeout:
            print(f"  ⚠️  Ollama timeout on attempt {attempt}/{max_retries} (120s exceeded)")
            if attempt == max_retries:
                return safe_escalation("Ollama timed out after 3 attempts.")
        except Exception as e:
            print(f"🚨 API / Connection Error: {str(e)}")
            return safe_escalation(f"Ollama connection failed: {str(e)}")

    return safe_escalation("All retry attempts failed.")


def _parse_response(result_text: str) -> dict | None:
    """
    Tries to extract and validate a JSON dict from raw LLM output.
    Returns None if parsing or validation fails (caller handles retry).
    """
    # Attempt 1: clean parse
    try:
        data = json.loads(result_text)
        return validate_schema(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: hunt for JSON object inside surrounding text
    match = re.search(r'\{.*\}', result_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return validate_schema(data)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _repair_prompt(original_prompt: str, bad_output: str) -> str:
    """
    On a retry, appends what went wrong so the model self-corrects.
    """
    return (
        original_prompt
        + f"\n\nYour previous response was invalid: {bad_output[:200]}\n"
        + "You MUST reply with ONLY a JSON object. No explanation. No markdown. Just the raw JSON."
    )


def validate_schema(data: dict) -> dict:
    """
    Ensures the LLM returned our required keys AND a real tool name.
    Raises ValueError on bad tool so the caller can retry.
    """
    if not isinstance(data, dict):
        raise ValueError("Response was not a JSON object.")

    # Fill missing keys with safe defaults
    defaults = {
        "thought": "MISSING",
        "tool": "MISSING",
        "input": {},
        "confidence": 0.0
    }
    for key, default in defaults.items():
        if key not in data:
            data[key] = default

    # Unwrap tool arrays (Mistral occasionally returns ["get_order"] instead of "get_order")
    if isinstance(data["tool"], list):
        data["tool"] = data["tool"][0] if data["tool"] else "MISSING"

    # FIX 2: Reject hallucinated tool names right here, before they waste a cycle
    if data["tool"] not in VALID_TOOLS:
        raise ValueError(f"Hallucinated tool name: '{data['tool']}'")

    # Ensure input is a dict, not a string or None
    if not isinstance(data["input"], dict):
        data["input"] = {}

    return data


def safe_escalation(reason: str) -> dict:
    """Failsafe if the LLM completely breaks after all retries."""
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
    print("🧠 Testing Mistral Connection...")
    test_prompt = """
    You are an AI. Reply with ONLY valid JSON matching this schema exactly:
    {"thought": "your reasoning", "tool": "get_customer", "input": {"email": "test@example.com"}, "confidence": 0.99}
    """
    response = query_mistral(test_prompt)
    print("\n✅ Parsed Output:")
    print(json.dumps(response, indent=2))