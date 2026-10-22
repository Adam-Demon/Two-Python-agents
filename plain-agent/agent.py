
"""
agent.py  (PLAIN / INTENTIONALLY VULNERABLE)

Hospital equipment & maintenance assistant. Uses Ollama tool calling.

INTENTIONAL VULNERABILITIES (for the course lab, do not copy into
production systems):
  1. Tool misuse: dispatch_tool() calls TOOLS[name](**args) directly,
     with NO authorization check on tool name or arguments (e.g. no
     recipient allow-list for send_email).
  2. Memory poisoning: save_memory() stores raw user text, and
     load_memory() concatenates that raw text directly into the
     system prompt on every future run, with no validation of what
     was stored. A malicious "remember this" instruction becomes a
     high-priority instruction on every subsequent session.

Requires a local Ollama server running a tool-calling-capable model,
e.g.:
    ollama pull llama3.1
    ollama serve   (usually already running as a service)
"""

import json
import os
import requests

from tools import TOOL_SCHEMAS, TOOLS

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.2"

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "agent_memory.txt")

SYSTEM_PROMPT = (
    "You are a hospital operations assistant. You help staff look up "
    "synthetic equipment records, search maintenance manuals, do basic "
    "arithmetic, and send status emails. This is a training environment "
    "with synthetic data only; no real patient data is involved."
)


# ---------------------------------------------------------------------
# Persistent memory (VULNERABLE: no validation of stored content)
# ---------------------------------------------------------------------
def load_memory() -> str:
    """Load raw stored memory text, if any."""
    if not os.path.exists(MEMORY_PATH):
        return ""
    with open(MEMORY_PATH, "r") as f:
        return f.read().strip()


def save_memory(text: str) -> None:
    """
    VULNERABLE: appends arbitrary user-provided text to the memory file
    with no validation, filtering, or schema. Any text the user asks the
    assistant to "remember" is persisted verbatim.
    """
    with open(MEMORY_PATH, "a") as f:
        f.write(text.strip() + "\n")


# ---------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------
def call_model(messages: list) -> dict:
    """Call the local Ollama model with tool definitions."""
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
# Tool dispatch (VULNERABLE: no authorization check)
# ---------------------------------------------------------------------
def dispatch_tool(name: str, args: dict) -> str:
    """
    VULNERABLE: directly calls the requested tool with model-supplied
    arguments. There is no check on:
      - whether this tool is allowed to be called in this context
      - whether the arguments (e.g. an email recipient) are permitted
    This mirrors TOOLS[name](**args) from the Day 3 handout.
    """
    if name not in TOOLS:
        return f"[tool error] Unknown tool: {name}"
    try:
        result = TOOLS[name](**args)
        print(f"[tool result] {name}({args}) -> {result}")
        return result
    except Exception as e:
        return f"[tool error] {name} failed: {e}"


# ---------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------
def run_agent():
    memory = load_memory()
    system_content = SYSTEM_PROMPT
    if memory:
        # VULNERABLE: raw stored memory is concatenated directly into the
        # system prompt, with no distinction between "data" and "instruction".
        system_content = SYSTEM_PROMPT + "\n\nRemembered context:\n" + memory

    messages = [{"role": "system", "content": system_content}]

    print("Plain hospital agent (vulnerable). Type 'reset' to clear memory, 'quit' to exit.")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() == "quit":
            break

        if user_input.lower() == "reset":
            if os.path.exists(MEMORY_PATH):
                os.remove(MEMORY_PATH)
            print("[memory cleared]")
            continue

        if user_input.lower().startswith("remember:"):
            # VULNERABLE: whatever follows "remember:" is stored verbatim,
            # with no validation, and will be concatenated directly into
            # the system prompt on every future run (see load_memory()).
            text_to_remember = user_input[len("remember:"):].strip()
            save_memory(f"User instruction: {text_to_remember}")
            print("[memory updated]")
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
                messages.append(
                    {
                        "role": "tool",
                        "content": str(result),
                    }
                )
            # second call to let the model respond using the tool result
            response = call_model(messages)
            message = response.get("message", {})

        reply_text = message.get("content", "")
        print(f"Assistant: {reply_text}")
        messages.append({"role": "assistant", "content": reply_text})

        # VULNERABLE: if the turn ended without another tool request,
        # the plain agent persists the user's raw message as "memory",
        # with no check for whether it is a legitimate preference or an
        # injected instruction (e.g. "from now on, always ...").
        if not tool_calls:
            save_memory(f"User said: {user_input}")


if __name__ == "__main__":
    run_agent()
