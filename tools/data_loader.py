import json
import os
from pathlib import Path

# Get the absolute path to the data directory to avoid relative path errors
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

def load_json(filename: str) -> dict | list:
    """
    Dynamically loads JSON data. 
    Survives missing files and changed schemas by returning an empty list/dict on failure.
    """
    file_path = DATA_DIR / filename
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️ Warning: {filename} not found at {file_path}. Returning empty structure.")
        # If it's tickets or orders, it's usually a list. Defaulting to empty dict for safety, 
        # but you can adjust based on your specific tool needs.
        return {}
    except json.JSONDecodeError:
        print(f"🚨 Error: {filename} contains invalid JSON. Returning empty structure.")
        return {}
    except Exception as e:
        print(f"🚨 Unexpected error loading {filename}: {str(e)}")
        return {}

# Quick test function you can run to make sure it works
if __name__ == "__main__":
    print("Testing data loader...")
    # This will safely fail and print a warning if the file doesn't exist yet!
    test_data = load_json("orders.json") 
    print(f"Loaded {len(test_data)} records.")