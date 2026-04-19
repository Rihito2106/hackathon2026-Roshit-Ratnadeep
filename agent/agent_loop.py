import json
import re
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
            if "error" not in result.lower() and "failed" not in result.lower() and "blocked" not in result.lower():
                return entry
    return None


def _is_repeat_action(action_history: list) -> bool:
    if len(action_history) < 2:
        return False
    last = action_history[-1]
    
    # WRITE tools that succeeded: any repeat is dangerous (double charge risk)
    if last["tool"] == "issue_refund" and "success" in str(last.get("result", "")).lower():
        second_last = action_history[-2]
        if second_last["tool"] == last["tool"] and second_last["input"] == last["input"]:
            return True

    # READ tools: only escalate after 3 identical calls in a row, not 2
    if last["tool"] in READ_TOOLS:
        if len(action_history) < 3:
            return False
        second_last = action_history[-2]
        third_last = action_history[-3]
        if (last["tool"] == second_last["tool"] == third_last["tool"] and
                last["input"] == second_last["input"] == third_last["input"]):
            return True

    return False

    # READ tier — only trigger after 3 identical calls in a row
    if last["tool"] in READ_TOOLS:
        if len(action_history) < 3:
            return False
        second_last = action_history[-2]
        third_last = action_history[-3]
        if (last["tool"] == second_last["tool"] == third_last["tool"] and
                last["input"] == second_last["input"] == third_last["input"]):
            return True

    return False


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

    # Primary: use what the model wrote
    if isinstance(response, dict) and "message" in response:
        return response["message"]

    # Last-resort fallback: extract amount and order ID from the result string
    # so we never paste raw "SUCCESS: ..." system text into a customer message
    action_result = str(terminal.get("result", "")) if terminal else ""
    amount_match = re.search(r'\$[\d.]+', action_result)
    amount = amount_match.group(0) if amount_match else "the full amount"
    order_match = re.search(r'ORD-\d+', action_result)
    order = order_match.group(0) if order_match else "your order"

    return (
        f"Great news — your refund of {amount} for {order} has been processed. "
        f"Please allow 3–5 business days for it to appear in your account. "
        f"Don't hesitate to reach out if you need anything else."
    )


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
  Scan Past Actions. If any WRITE/ACT tool result does NOT contain "error", "failed", or "blocked":
  → Your ONLY valid next tool is send_reply. Do not call any other tool.

RULE 2 — REPLY CONTENT IS ANCHORED TO COMPLETED ACTIONS ONLY:
  Your send_reply message MUST open by stating what was completed.
  ✅ "Your refund of $X has been issued."
  ❌ Mentioning warranty, policy, or any topic not in the completed action result.
  ❌ Claiming a refund was issued if issue_refund does not appear in Past Actions.

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

RULE 8 — NEVER CONTRADICT SYSTEM RESULTS:
  If check_refund_eligibility returned eligible:true, you MUST proceed with issue_refund.
  You are NEVER allowed to tell a customer they are ineligible if the system said eligible.
  You are NEVER allowed to invent policies (e.g. "premium members only") not present in Past Actions.

RULE 9 — REFUND CONSENT: NEVER call issue_refund unless the customer explicitly uses the word "refund". If they ask for a "replacement", "exchange", or "tracking", you MUST NOT issue a refund.
"""


def process_ticket(ticket_data: dict) -> dict:
    """The Core ReAct Loop: Think, Act, Observe — with deterministic guardrails."""
    ticket_id = ticket_data.get("ticket_id", "UNKNOWN")
    print(f"\n--- 🚀 Starting Agent Loop for Ticket: {ticket_id} ---")

    max_iterations = 7
    iteration = 0
    resolved = False
    action_history = []

    # Tracks which order IDs have been refunded this session.
    # Prevents double-charge if the model calls issue_refund twice for the same order.
    issued_orders = set()

    while not resolved and iteration < max_iterations:
        iteration += 1
        print(f"\n[Cycle {iteration}]")

        # ── GUARDRAIL A: Infinite loop / double-charge detection ──────────────
        # Calls the module-level _is_repeat_action — NOT a nested version.
        # Fires before any LLM call so stuck agents exit fast and cleanly.
        if _is_repeat_action(action_history):
            last = action_history[-1]
            print(f"🛡️  GUARDRAIL A: Repeat action on '{last['tool']}' — forcing escalation.")
            obs = escalate(
                ticket_id=ticket_id,
                summary=f"Agent stuck repeating '{last['tool']}' with input {last['input']}. Manual review required.",
                priority="high"
            )
            action_history.append({
                "cycle": iteration,
                "tool": "escalate",
                "input": {"ticket_id": ticket_id},
                "result": obs
            })
            resolved = True
            print(f"\n✅ Ticket {ticket_id} Resolved via: guardrail A → escalate")
            break
        # ─────────────────────────────────────────────────────────────────────

        # ── GUARDRAIL B: Deterministic terminal state check ───────────────────
        # If a terminal action already succeeded, skip LLM reasoning entirely.
        terminal_entry = _terminal_action_succeeded(action_history)
        already_replied = any(e["tool"] == "send_reply" for e in action_history)

        if terminal_entry and not already_replied:
            print("🛡️  GUARDRAIL B: Terminal action detected — forcing send_reply.")
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
            print(f"\n✅ Ticket {ticket_id} Resolved via: guardrail B → send_reply")
            break
        # ─────────────────────────────────────────────────────────────────────

        # 1. THOUGHT & ACTION
        prompt = _build_prompt(ticket_data, action_history)
        print("🤔 THOUGHT: Asking Mistral...")
        llm_response = query_mistral(prompt)
        print(f"  -> {llm_response.get('thought')}")

        tool_name = llm_response.get("tool")
        if isinstance(tool_name, list):
            tool_name = tool_name[0]
        tool_input = llm_response.get("input", {})

        # ── GUARDRAIL C: Block READ tools after a write action has succeeded ──
        if tool_name in READ_TOOLS and terminal_entry:
            print(f"🛡️  GUARDRAIL C: Blocked READ '{tool_name}' after terminal action.")
            action_history.append({
                "cycle": iteration,
                "tool": tool_name,
                "input": tool_input,
                "result": "BLOCKED: A system action has already succeeded. You MUST call send_reply next."
            })
            continue
        # ─────────────────────────────────────────────────────────────────────

        # ── GUARDRAIL D: Block false refund claims in send_reply ──────────────
        # Prevents agent from telling customer a refund happened when it didn't.
        # Replace the existing guardrail D block with this:
        if tool_name == "send_reply":
            msg = tool_input.get("message", "").lower()
            refund_words = ["has been issued", "successfully processed", "refund of $"]
            refund_claimed = any(w in msg for w in refund_words)

            # Pass 1: issue_refund succeeded this session
            refund_done_this_session = any(
                e["tool"] == "issue_refund" and "success" in str(e.get("result", "")).lower()
                for e in action_history
            )
            # Pass 2: get_order already showed refund_status = "refunded" (pre-existing refund)
            preexisting_refund = any(
                isinstance(e.get("result"), dict) and e["result"].get("refund_status") == "refunded"
                for e in action_history
            )

            if refund_claimed and not refund_done_this_session and not preexisting_refund:
                print("🛡️  GUARDRAIL: Blocked false refund claim — no completed issue_refund in history.")
                action_history.append({
                    "cycle": iteration,
                    "tool": "send_reply",
                    "input": tool_input,
                    "result": "BLOCKED: Do not claim a refund was issued until issue_refund succeeds. Call issue_refund first."
                })
                continue
        # ─────────────────────────────────────────────────────────────────────

        # ── GUARDRAIL E: Block duplicate issue_refund (double-charge prevention)
        if tool_name == "issue_refund":
            order_id = tool_input.get("order_id", "")
            if order_id in issued_orders:
                print(f"🛡️  GUARDRAIL E: Blocked duplicate issue_refund for {order_id}.")
                action_history.append({
                    "cycle": iteration,
                    "tool": "issue_refund",
                    "input": tool_input,
                    "result": f"BLOCKED: Refund for {order_id} was already issued this session. Call send_reply next."
                })
                continue
        # ─────────────────────────────────────────────────────────────────────

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

        # Register successfully refunded orders immediately after execution
        if tool_name == "issue_refund" and "success" in str(observation).lower():
            order_id = tool_input.get("order_id", "")
            if order_id:
                issued_orders.add(order_id)

        action_history.append({
            "cycle": iteration,
            "tool": tool_name,
            "input": tool_input,
            "result": observation
        })

        # ── POST-OBSERVE GUARDRAIL: Fire reply if terminal success just happened
        # Guardrail B only runs at the TOP of the next cycle. If issue_refund
        # succeeds on cycle 7 (the last allowed cycle), the while condition exits
        # before B ever gets another chance. This catches that exact case.
        if tool_name in TERMINAL_WRITE_TOOLS and "success" in str(observation).lower():
            if not any(e["tool"] == "send_reply" for e in action_history):
                print("🛡️  GUARDRAIL POST-OBSERVE: Terminal success — firing reply immediately.")
                message = _force_send_reply(ticket_data, action_history)
                send_obs = send_reply(ticket_id=ticket_id, message=message)
                print(f"📨 FORCED REPLY: {message}")
                action_history.append({
                    "cycle": iteration,
                    "tool": "send_reply",
                    "input": {"ticket_id": ticket_id, "message": message},
                    "result": send_obs
                })
                resolved = True
                print(f"\n✅ Ticket {ticket_id} Resolved via: post-observe guardrail → send_reply")
                break
        # ─────────────────────────────────────────────────────────────────────

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