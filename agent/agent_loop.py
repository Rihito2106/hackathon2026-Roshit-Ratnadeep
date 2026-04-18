import json
from agent.llm_engine import query_mistral
from tools.read_tools import get_order, get_customer, get_product, search_knowledge_base
from tools.write_tools import check_refund_eligibility, issue_refund, send_reply, escalate

TOOL_MAP = {
    "get_order": get_order,
    "get_customer": get_customer,
    "get_product": get_product,
    "search_knowledge_base": search_knowledge_base,
    "check_refund_eligibility": check_refund_eligibility,
    "issue_refund": issue_refund,
    "send_reply": send_reply,
    "escalate": escalate
}

# Tools that mean "we're done with system actions, now communicate"
TERMINAL_WRITE_TOOLS = {"issue_refund", "escalate"}

# Tools that fully close the loop
CLOSING_TOOLS = {"send_reply", "escalate"}

# After one of these succeeds, no READ tool should ever be called again
READ_TOOLS = {"get_order", "get_customer", "get_product", "search_knowledge_base"}


def _terminal_action_succeeded(action_history: list) -> dict | None:
    """
    Returns the first successful terminal write action if one exists,
    otherwise None. This is the single source of truth for 'are we done acting?'
    """
    for entry in action_history:
        if entry["tool"] in TERMINAL_WRITE_TOOLS:
            result = str(entry.get("result", ""))
            # Check for explicit failure signals — don't assume success
            if "error" not in result.lower() and "failed" not in result.lower():
                return entry
    return None


def _force_send_reply(ticket_data: dict, action_history: list) -> str:
    """
    Bypass the full ReAct loop entirely.
    Only asks the model to draft a reply message, given what was done.
    This prevents the model from re-reasoning about the ticket content.
    """
    terminal = _terminal_action_succeeded(action_history)
    
    forced_prompt = f"""
A customer support action has been completed. Your ONLY job is to write 
a short, friendly reply to the customer summarizing what was done.

Completed Action: {json.dumps(terminal)}
Ticket: {json.dumps(ticket_data)}

STRICT RULES FOR THIS REPLY:
- Open with the completed action (e.g. "Good news — your refund of $X has been processed.")
- Do NOT mention warranty, policy, or any topic not directly related to the completed action.
- Do NOT ask the customer any questions.
- Keep it to 3 sentences max.

Reply ONLY with this JSON and nothing else:
{{"message": "your reply here"}}
"""
    response = query_mistral(forced_prompt)
    
    # Defensive fallback if the model misbehaves even on this narrow prompt
    if isinstance(response, dict) and "message" in response:
        return response["message"]
    
    # Last-resort hardcoded fallback so the ticket always closes
    action_str = terminal.get("result", "your request has been processed")
    return f"Good news! {action_str}. Your case is now resolved. Please reach out if you need anything else."


def _build_prompt(ticket_data: dict, action_history: list) -> str:
    return f"""
You are an Autonomous Support Resolution Agent.

Ticket Details: {json.dumps(ticket_data)}
Past Actions & Results: {json.dumps(action_history)}

Analyze the Past Actions first, then the ticket. Decide the SINGLE next immediate step.

TOOL INSTRUCTION MANUAL (STRICT SCHEMA):
READ / LOOKUP:
  - get_order:             {{"order_id": "string"}}
  - get_customer:          {{"email": "string"}}
  - get_product:           {{"product_id": "string"}}
  - search_knowledge_base: {{"query": "string"}}

WRITE / ACT:
  - check_refund_eligibility: {{"order_id": "string"}}
  - issue_refund:             {{"order_id": "string", "amount": float}}
  - send_reply:               {{"ticket_id": "string", "message": "string"}}
  - escalate:                 {{"ticket_id": "string", "summary": "string", "priority": "low/medium/high/urgent"}}

Reply ONLY with this JSON and nothing else:
{{
    "thought": "step-by-step reasoning for THIS turn only",
    "tool": "single tool name string",
    "input": {{"key": "value"}},
    "confidence": 0.0
}}

CRITICAL RULES — read ALL before deciding:

RULE 1 — TERMINAL STATE CHECK (evaluate this FIRST):
  Scan Past Actions. If any WRITE/ACT tool result does NOT contain "error" or "failed":
  → Your ONLY valid next tool is send_reply. Do not call any other tool.

RULE 2 — REPLY CONTENT IS ANCHORED TO COMPLETED ACTIONS ONLY:
  Your send_reply message MUST open by stating what was completed.
  ✅ "Your refund of $X has been issued."
  ❌ Mentioning warranty, policy, or any topic not in the completed action result.

RULE 3 — NO LOOKUPS AFTER A WRITE ACTION SUCCEEDS:
  Once any WRITE/ACT tool succeeds, never call a READ/LOOKUP tool again.
  The reason the customer gave you (broken, wrong item, late) is CLOSED once actioned.

RULE 4 — STRICT SEQUENCING & NO GUESSING (refund flow):
  The exact flow MUST be: get_order (to find the float amount) → check_refund_eligibility → issue_refund → send_reply.
  NEVER guess, hallucinate, or use strings for the 'amount' parameter. You must fetch it from get_order first.

RULE 5 — NO CHATBOT BEHAVIOR:
  Never use send_reply to ask questions or gather information mid-workflow.
  send_reply is the FINAL step only, after all system actions are complete.

RULE 6 — SINGLE TOOL ONLY:
  The 'tool' field is a single string. Decide only the immediate next step.

RULE 7 — ESCALATE IF BLOCKED:
  If a WRITE tool returns an error after one attempt, call escalate immediately.
  Do not retry failed actions more than once.
"""


def process_ticket(ticket_data: dict) -> dict:
    """The Core ReAct Loop: Think, Act, Observe — with deterministic guardrails."""
    ticket_id = ticket_data.get("ticket_id", "UNKNOWN")
    print(f"\n--- 🚀 Starting Agent Loop for Ticket: {ticket_id} ---")

    max_iterations = 7  # Raised slightly since we now abort early via guardrails
    iteration = 0
    resolved = False
    action_history = []

    while not resolved and iteration < max_iterations:
        iteration += 1
        print(f"\n[Cycle {iteration}]")

        # ── GUARDRAIL: Deterministic terminal state check ──────────────────────
        # If a terminal action already succeeded, skip LLM reasoning entirely.
        # The model cannot drift here because we're not asking it anything.
        terminal_entry = _terminal_action_succeeded(action_history)
        already_replied = any(e["tool"] == "send_reply" for e in action_history)

        if terminal_entry and not already_replied:
            print("🛡️  GUARDRAIL: Terminal action detected — forcing send_reply.")
            message = _force_send_reply(ticket_data, action_history)
            observation = send_reply(ticket_id=ticket_id, message=message)
            print(f"📨 FORCED REPLY: {message}")
            print(f"👀 OBSERVE: {observation}")
            action_history.append({
                "cycle": iteration,
                "tool": "send_reply",
                "input": {"ticket_id": ticket_id, "message": message},
                "result": observation
            })
            resolved = True
            print(f"\n✅ Ticket {ticket_id} Resolved via: guardrail → send_reply")
            break
        # ───────────────────────────────────────────────────────────────────────

        # 1. THOUGHT & ACTION
        prompt = _build_prompt(ticket_data, action_history)
        print("🤔 THOUGHT: Asking Mistral...")
        llm_response = query_mistral(prompt)
        print(f"  -> {llm_response.get('thought')}")

        tool_name = llm_response.get("tool")
        if isinstance(tool_name, list):
            tool_name = tool_name[0]  # Defensive fix for Mistral returning arrays
        tool_input = llm_response.get("input", {})

        # ── GUARDRAIL: Block READ tools after a write action has succeeded ─────
        if tool_name in READ_TOOLS and terminal_entry:
            print(f"🛡️  GUARDRAIL: Blocked disallowed READ call '{tool_name}' after terminal action.")
            # Inject a fake observation to redirect the model next cycle
            action_history.append({
                "cycle": iteration,
                "tool": tool_name,
                "input": tool_input,
                "result": "BLOCKED: A system action has already succeeded. You MUST call send_reply next."
            })
            continue
        # ───────────────────────────────────────────────────────────────────────

        print(f"🛠️  ACTION: Executing {tool_name} with {tool_input}")

        # 2. OBSERVE
        if tool_name in TOOL_MAP:
            try:
                observation = TOOL_MAP[tool_name](**tool_input)
            except Exception as e:
                observation = f"Tool Execution Failed: {str(e)}"
        else:
            observation = f"Error: Tool '{tool_name}' does not exist."

        print(f"👀 OBSERVE: {observation}")

        action_history.append({
            "cycle": iteration,
            "tool": tool_name,
            "input": tool_input,
            "result": observation
        })

        # 3. RESOLVE CHECK
        if tool_name in CLOSING_TOOLS:
            resolved = True
            print(f"\n✅ Ticket {ticket_id} Resolved via: {tool_name}")

    if not resolved:
        print(f"\n🚨 CRITICAL: Max iterations reached for {ticket_id}. Forcing escalation.")
        escalate(
            ticket_id=ticket_id,
            summary="Agent exceeded max iterations without resolving ticket.",
            priority="high"
        )

    return {"status": "complete", "ticket_id": ticket_id, "history": action_history}


if __name__ == "__main__":
    mock_ticket = {
        "ticket_id": "TKT-001",
        "customer_email": "alice.turner@email.com",
        "issue": "I want to refund my order ORD-1001, it arrived broken."
    }
    process_ticket(mock_ticket)