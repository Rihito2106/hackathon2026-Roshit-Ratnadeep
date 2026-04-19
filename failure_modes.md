# 🚨 Failure Modes & Chaos Engineering Analysis

Building an autonomous agent with a local 7B parameter model (Mistral) requires anticipating both LLM hallucinations and real-world API instability. Instead of relying purely on prompt engineering, this system utilizes a "Chaos Engine" and deterministic Python guardrails to handle failures gracefully.

Below are three documented failure scenarios observed during testing and how the system handles them.

---

### Failure Mode 1: The "Amnesia Loop" (Stuck ReAct Loop)
* **The Scenario:** Smaller LLMs occasionally forget a required parameter for a WRITE tool (e.g., forgetting the `amount` float for `issue_refund`). When the tool returns an error, the agent panics and repeatedly calls a READ tool (like `get_order`) over and over again trying to find the missing data, creating an infinite loop.
* **Evidence in Audit Log:** Observed in **TKT-004** and **TKT-013**.
* **System Response (Guardrail A):** The system does not allow the loop to run indefinitely. Before every LLM call, a deterministic Python guardrail checks the `action_history`. If it detects three identical, consecutive READ calls (or any duplicate WRITE calls), it physically intercepts the ReAct loop, forces a `safe_escalation` to a human agent with a 'High' priority flag, and cleanly resolves the ticket without crashing the application.

### Failure Mode 2: External API Instability & 502 Errors
* **The Scenario:** In a production environment, downstream services (like billing or shipping APIs) frequently time out or return 502 Bad Gateway errors. A fragile agent script would fatally crash when an awaited JSON response fails.
* **Evidence in Audit Log:** Observed during the `check_refund_eligibility` call in **TKT-014**.
* **System Response:** The system handles this at two levels:
  1. **Tool Level:** The `TOOL_MAP` execution block is wrapped in a `try/except` block. If a tool fails or throws an error string (like the 502 error in TKT-014), the Python script converts it into a plain text observation and feeds it back to the LLM so the agent knows the action failed. 
  2. **Inference Level:** If the local Ollama LLM itself times out due to heavy concurrent load, `llm_engine.py` implements a 3-attempt retry budget to prevent worker crashes.

### Failure Mode 3: Schema Hallucination & Missing Arguments
* **The Scenario:** Local 7B models sometimes format their JSON correctly but hallucinate the function signature, forgetting required positional arguments entirely.
* **Evidence in Audit Log:** Observed in **TKT-002** and **TKT-016**, where the model called `send_reply` but forgot to include the mandatory `ticket_id` parameter.
* **System Response & Future Mitigation:** * *Current State:* The Python execution block catches the missing argument exception (`TypeError: send_reply() missing 1 required positional argument`), logs it as a failed tool execution, and ensures the script doesn't crash. 
  * *V2 Architecture Fix:* In a production V2, the `llm_engine.py` schema validator would be expanded to not only check if the JSON is valid, but to validate the exact keys inside the `input` dictionary against a Pydantic model *before* passing it to the tool execution block.