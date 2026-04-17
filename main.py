import time
from tools.read_tools import get_order, get_customer, get_product, search_knowledge_base
from tools.write_tools import check_refund_eligibility, issue_refund, send_reply, escalate

def test_read_tools():
    print("\n--- 🔍 TESTING READ TOOLS ---")
    # Valid lookups
    print("Valid Order:", get_order("ORD-1001"))
    print("Valid Customer:", get_customer("alice.turner@email.com")) # Adjust email based on your customers.json
    
    # Invalid lookups (Should return safe error strings, NOT crash)
    print("Invalid Order:", get_order("ORD-9999"))
    
    # Knowledge Base Search
    print("KB Search 'refund':", search_knowledge_base("refund policy time"))

def test_write_tools():
    print("\n--- 🔥 TESTING WRITE TOOLS (CHAOS ENGINE) ---")
    
    # Test the Chaos Engine by calling it 5 times
    print("Testing check_refund_eligibility (Simulating 5 API calls):")
    for i in range(1, 6):
        try:
            result = check_refund_eligibility("ORD-1001")
            print(f"  Attempt {i}: SUCCESS - {result}")
        except TimeoutError as e:
            print(f"  Attempt {i}: 🚨 CAUGHT TIMEOUT - {e}")
        except Exception as e:
            print(f"  Attempt {i}: 🚨 CAUGHT UNEXPECTED ERROR - {e}")
        time.sleep(0.5)

    # Test the other write tools
    print("\nTesting Escalate:")
    print(" ", escalate("TKT-123", "Customer very angry about delayed laptop.", "URGENT"))

if __name__ == "__main__":
    print("Starting Day 1 Tool Stress Test...\n")
    test_read_tools()
    test_write_tools()
    print("\n✅ Day 1 Stress Test Complete!")