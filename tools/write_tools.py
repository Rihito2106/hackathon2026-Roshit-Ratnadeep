import random
import time

def check_refund_eligibility(order_id: str) -> dict:
    """
    Checks if an order is eligible for a refund. 
    Intentionally designed to simulate real-world API instability.
    """
    # Simulate a slight network delay
    time.sleep(random.uniform(0.1, 0.5))
    
    # 20% chance of catastrophic failure to test agent recovery
    chaos_roll = random.random()
    if chaos_roll < 0.1:
        raise TimeoutError(f"API Timeout: check_refund_eligibility failed to respond for order {order_id}.")
    elif chaos_roll < 0.2:
        return {"error": "502 Bad Gateway - Malformed data received from billing service."}
        
    # Standard successful mock response
    return {"eligible": True, "reason": "System verification complete.", "order_id": order_id}

def issue_refund(order_id: str, amount: float) -> str:
    """
    IRREVERSIBLE action to issue a refund. 
    The agent's reasoning loop MUST verify eligibility before calling this.
    """
    # In a real system this hits Stripe/PayPal. Here we mock success.
    # If the audit log shows the agent called this without calling check_refund_eligibility first, you fail!
    return f"SUCCESS: Refund of ${amount} issued for order {order_id}."

def send_reply(ticket_id: str, message: str) -> str:
    """Sends a resolution response to the customer."""
    return f"Message sent to customer for ticket {ticket_id}: '{message}'"

def escalate(ticket_id: str, summary: str, priority: str) -> str:
    """Routes the ticket to a human agent with full context."""
    valid_priorities = ["low", "medium", "high", "urgent"]
    # Defensive check in case the LLM hallucinates a weird priority level
    if priority.lower() not in valid_priorities:
        priority = "medium" 
        
    return f"ESCALATED (Priority: {priority.upper()}): Ticket {ticket_id} routed to human. Summary: {summary}"