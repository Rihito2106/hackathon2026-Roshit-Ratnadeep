# 🤖 Autonomous Support Resolution Agent
**Agentic AI Hackathon 2026 Submission**

An autonomous, fault-tolerant AI agent built to ingest, classify, resolve, and log customer support tickets concurrently. Designed with strict deterministic guardrails to prevent LLM hallucinations, infinite loops, and chatbot-style conversational drift.

## 🛠️ Tech Stack
* **Language:** Python 3.10+
* **LLM Engine:** Mistral 7B (Local via Ollama)
* **Architecture:** Custom ReAct (Reason + Act) Loop with Deterministic State Management
* **Data Layer:** Local JSON Mock APIs (Simulating Order/Customer DBs and Knowledge Base)
* **Concurrency:** Native Python `ThreadPoolExecutor` (Bounded)

## ⚙️ Setup Instructions
To run this agent locally, you need to configure your environment to run the local Mistral model:

1. **Install Python:** Ensure you have Python 3.10 or higher installed on your machine.
2. **Install Ollama:** Download and install [Ollama](https://ollama.com/) to run local language models.
3. **Pull the Model:** Open your terminal and pull the Mistral 7B model by running:
   `ollama run mistral`
4. **Clone Repository:** Ensure all data files (`tickets.json`, `orders.json`, etc.) are located in the `data/` folder and your Python scripts are in the root and `agent/` directories.

## 🚀 How to Run the Agent
Once Ollama is running in the background, you can execute the entire 20-ticket queue autonomously with a single command. 

Open your terminal in the root directory of the project and run:
```bash
python main.py
```

*Note: The system will automatically ingest `data/tickets.json`, process the queue using 3 concurrent workers, and generate a final flight recorder in `logs/audit_log.json`.*

## 🧠 Key Engineering Features
To meet the strict "Production Readiness" requirements, this agent prioritizes systems engineering over prompt engineering:

**1. Bounded Concurrency**
The agent processes the ticket queue concurrently rather than sequentially. To prevent local hardware from crashing during heavy LLM inference, it uses a bounded `ThreadPoolExecutor` locked to `max_workers=3`. 

**2. The "Chaos Engine" (Anti-Break Parser)**
Local 7B models occasionally fail to output valid JSON or pass incorrect parameters. Instead of allowing a malformed LLM response to crash the entire application, the custom `llm_engine.py` features a robust regex parser and retry budget. If the model completely fails, the script executes a `safe_escalation` protocol—routing the broken ticket to a human while keeping the concurrent workers alive to finish the queue.

**3. Deterministic Guardrails**
LLMs naturally drift into "chatbot" behavior or infinite loops. This agent uses hardcoded Python guardrails that scan the `action_history` *before* every LLM call:
* **The Terminal Block:** If a system action (like `issue_refund`) succeeds, Python physically intercepts the loop and forces the agent to send a reply and close the ticket, preventing over-investigation.
* **Amnesia Loop Prevention:** If the agent gets stuck repeating the same tool call, the system detects the repetition and forces an immediate escalation.

## 📂 Deliverables Checklist
- [x] **`README.md`**: Setup instructions, run commands, and tech stack.
- [x] **`architecture.pdf`**: 1-page diagram of the agent loop and tool design.
- [x] **`failure_modes.md`**: Documentation of specific failure scenarios and system responses.
- [x] **`logs/audit_log.json`**: The complete flight recorder showing tool calls and reasoning for all 20 tickets.
- [x] **`demo_video.mp4`**: A recorded screen capture of the agent processing the queue.