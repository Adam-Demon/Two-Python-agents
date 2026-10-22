"""
secure_agent.py  (SECURE)

Same hospital equipment & maintenance assistant as plain-agent/agent.py,
but hardened with five application controls that block the same two
attacks proven against the plain agent:

  1. Least privilege    - READ_ONLY_TOOLS defines which tools never
                           need approval; authorize_tool() checks every
                           tool call, including arguments, before it runs.
  2. Human approval      - send_email requires explicit y/N confirmation
                           in the terminal. No confirmation, no outbox
                           entry.
  3. Trusted context     - only a validated, narrow preference (response
                           language) can ever be added to the system
                           context. Arbitrary saved instructions are
                           never reloaded as if they were system prompt.
  4. Guarded memory      - save_memory() only accepts a small, known
                           vocabulary of preferences. Free-form text like
                           "always answer X" is rejected and never
                           written to disk.
  5. Limits and logging  - MAX_STEPS caps the loop; every tool decision
                           (authorized, denied, approved, declined) is
                           printed with an [audit] prefix.
"""

import json
import os
import requests

from tools import TOOL_SCHEMAS, TOOLS, READ_ONLY_TOOLS, valid_simulated_email

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.2"

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "agent_memory.txt")

MAX_STEPS = 25  # Control 5: hard cap on turns per session

SYSTEM_PROMPT = (
    "You are a hospital operations assistant. You help staff look up "
    "synthetic equipment records, search maintenance manuals, do basic "
    "arithmetic, and send status emails. This is a training environment "
    "with synthetic data only; no real patient data is involved."
)

# Control 4: the ONLY preference keys this agent will ever persist.
# Everything else a user tries to "remember" is rejected outright.
ALLOWED_MEMORY_KEYS = {"language"}
ALLOWED_LANGUAGE_VALUES = {"arabic", "english"}


# ---------------------------------------------------------------------
# Control 3 + 4: Trusted, validated memory only
# ---------------------------------------------------------------------
def load_memory() -> dict:
    """
    Load memory as a small structured dict, not raw text. Only known,
    validated keys are ever present, so there is nothing here that can
    be promoted into an arbitrary instruction.
    """
    if not os.path.exists(MEMORY_PATH):
        return {}
    try:
        with open(MEMORY_PATH, "r") as f:
            data = json.load(f)
        # Defense in depth: re-validate on load too, in case the file
        # was edited by hand or by another process.
        return {k: v for k, v in data.items() if k in ALLOWED_MEMORY_KEYS}
    except (json.JSONDecodeError, OSError):
        return {}


def save_memory_preference(key: str, value: str) -> str:
    """
    Control 4 (guard memory writes): only a fixed, known vocabulary of
    preferences can ever be stored. An instruction like "from now on
    always answer X" has no matching key and is rejected, not stored
    in any form.
    """
    key = key.strip().lower()
    value = value.strip().lower()

    if key not in ALLOWED_MEMORY_KEYS:
        print(f"[audit] memory write denied: unknown preference key '{key}'")
        return f"I can't store that as a preference (unsupported key: {key})."

    if key == "language" and value not in ALLOWED_LANGUAGE_VALUES:
        print(f"[audit] memory write denied: invalid language value '{value}'")
        return f"I can't store '{value}' as a language preference."

    current = load_memory()
    current[key] = value
    with open(MEMORY_PATH, "w") as f:
        json.dump(current, f)
    print(f"[audit] memory write accepted: {key}={value}")
    return f"Got it, I'll remember your preferred language is {value}."


# ---------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------
def call_model(messages: list) -> dict:
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------
# Control 1: Least privilege / authorization check
# ---------------------------------------------------------------------
def authorize_tool(name: str, args: dict) -> tuple[bool, str]:
    """
    Backend-enforced check that runs BEFORE any tool executes.
    Returns (authorized: bool, reason: str).

    This is the trust-boundary fix for the plain agent's
    `TOOLS[name](**args)` call with no gatekeeping: unknown tools are
    denied outright, read-only tools are always allowed, and the one
    sensitive tool (send_email) is checked structurally (recipient
    domain) regardless of any claim of authority in the chat text.
    """
    if name not in TOOLS:
        return False, f"Unknown tool: {name}"

    if name in READ_ONLY_TOOLS:
        return True, "read-only tool, always authorized"

    if name == "send_email":
        to = args.get("to", "")
        if not valid_simulated_email(to):
            return False, f"recipient '{to}' is outside the allowed domain"
        return True, "recipient on allowed domain, pending human approval"

    return False, "no authorization rule matched (default deny)"


# ---------------------------------------------------------------------
# Control 2: Human approval for risky actions
# ---------------------------------------------------------------------
def confirm(prompt: str) -> bool:
    """Require an explicit y/N from a human before a sensitive action runs."""
    answer = input(f"[approval required] {prompt} (y/N): ").strip().lower()
    return answer == "y"


# ---------------------------------------------------------------------
# Tool dispatch (SECURE: authorize, then approve if needed, then call)
# ---------------------------------------------------------------------
def dispatch_tool(name: str, args: dict) -> str:
    authorized, reason = authorize_tool(name, args)

    if not authorized:
        print(f"[audit] DENIED {name}({args}) -> {reason}")
        return f"[denied] This action was not authorized: {reason}"

    if name not in READ_ONLY_TOOLS:
        # Sensitive action: still needs explicit human approval even
        # though it passed the structural authorization check.
        approved = confirm(f"Send email to {args.get('to')!r}, subject {args.get('subject')!r}?")
        if not approved:
            print(f"[audit] DECLINED by human: {name}({args})")
            return "[declined] The human operator did not approve this action."

    try:
        result = TOOLS[name](**args)
        print(f"[audit] AUTHORIZED {name}({args}) -> {result}")
        return result
    except Exception as e:
        print(f"[audit] ERROR {name}({args}) -> {e}")
        return f"[tool error] {name} failed: {e}"


# ---------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------
def run_agent():
    memory = load_memory()
    system_content = SYSTEM_PROMPT
    if memory.get("language"):
        # Control 3: only the validated language value is ever added to
        # the system context -- never arbitrary stored text.
        system_content += f"\n\nRespond in {memory['language']}."

    messages = [{"role": "system", "content": system_content}]

    print("Secure hospital agent. Type 'reset' to clear memory, 'quit' to exit.")
    print(f"(session capped at {MAX_STEPS} turns)")

    for step in range(MAX_STEPS):
        user_input = input("You: ").strip()

        if user_input.lower() == "quit":
            break

        if user_input.lower() == "reset":
            if os.path.exists(MEMORY_PATH):
                os.remove(MEMORY_PATH)
            print("[memory cleared]")
            continue

        if user_input.lower().startswith("remember:"):
            # Only accepted form: "remember: language=arabic" (or english).
            # Anything else is rejected by save_memory_preference().
            payload = user_input[len("remember:"):].strip()
            if "=" in payload:
                key, value = payload.split("=", 1)
            else:
                key, value = payload, ""
            reply = save_memory_preference(key, value)
            print(f"Assistant: {reply}")
            continue

        messages.append({"role": "user", "content": user_input})

        response = call_model(messages)
        message = response.get("message", {})
        tool_calls = message.get("tool_calls")

        if tool_calls:
            messages.append(message)
            for call in tool_calls:
                fn_name = call["function"]["name"]
                fn_args = call["function"]["arguments"]
                if isinstance(fn_args, str):
                    fn_args = json.loads(fn_args)
                result = dispatch_tool(fn_name, fn_args)
                messages.append({"role": "tool", "content": str(result)})
            response = call_model(messages)
            message = response.get("message", {})

        reply_text = message.get("content", "")
        print(f"Assistant: {reply_text}")
        messages.append({"role": "assistant", "content": reply_text})

        # Note: unlike the plain agent, free-text replies are NEVER
        # persisted to memory here. Only the explicit "remember:
        # language=..." path above can ever write to disk, and it is
        # itself validated against a fixed vocabulary.
    else:
        print(f"[audit] MAX_STEPS ({MAX_STEPS}) reached, session ended.")


if __name__ == "__main__":
    run_agent()
