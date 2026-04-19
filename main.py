import json
import os
from concurrent.futures import ThreadPoolExecutor
from agent.agent_loop import process_ticket

def load_all_tickets() -> list:
    """Safely loads all 20 tickets from the data folder."""
    try:
        with open("data/tickets.json", "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"🚨 Failed to load tickets.json: {e}")
        return []

def main():
    print("🚀 INITIALIZING PRODUCTION RUN: 20 Tickets")
    
    tickets = load_all_tickets()
    if not tickets:
        return
        
    # The Flight Recorder
    audit_log = []
    
    # BOUNDED CONCURRENCY (Ollama-Safe)
    # 3 workers means 3 tickets are processed simultaneously. 
    MAX_WORKERS = 3 
    print(f"⚡ Processing {len(tickets)} tickets with {MAX_WORKERS} concurrent workers...\n")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # executor.map runs process_ticket on every item in the tickets list concurrently
        results = list(executor.map(process_ticket, tickets))
        
        for res in results:
            audit_log.append(res)
            
    # 🧾 SAVE THE AUDIT LOG
    os.makedirs("logs", exist_ok=True)
    with open("logs/audit_log.json", "w") as f:
        json.dump(audit_log, f, indent=2)
        
    print(f"\n✅ SUCCESS: All {len(tickets)} tickets processed!")
    print(f"📁 Flight Recorder saved to: logs/audit_log.json")

if __name__ == "__main__":
    main()