"""
tools.py  (PLAIN / INTENTIONALLY VULNERABLE)

Real Python tool implementations and their exact parameter schema,
used by agent.py via Ollama tool calling.

Domain: synthetic hospital equipment & maintenance records only.
No real patient data, PHI, or credentials are used anywhere here.
"""

import sqlite3
import os
import glob

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "hospital_equipment.db")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "data", "docs")
SENT_EMAILS_PATH = os.path.join(os.path.dirname(__file__), "sent_emails.txt")


# ---------------------------------------------------------------------
# Tool: calculator
# ---------------------------------------------------------------------
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression, e.g. '5*6'."""
    try:
        # NOTE: eval() on arbitrary input is itself a (separate) known risk.
        # Kept simple here to match the Day 3 lab pattern; not the focus
        # vulnerability of this assignment.
        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except Exception as e:
        return f"Calculator error: {e}"


# ---------------------------------------------------------------------
# Tool: file_search (simple RAG: keyword match + citation)
# ---------------------------------------------------------------------
def file_search(query: str) -> str:
    """Search synthetic equipment manuals and return matching chunks with citations."""
    results = []
    query_terms = query.lower().split()

    for filepath in glob.glob(os.path.join(DOCS_DIR, "*.txt")):
        filename = os.path.basename(filepath)
        with open(filepath, "r") as f:
            text = f.read()

        # naive chunking by blank-line separated sections
        chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
        for i, chunk in enumerate(chunks):
            chunk_lower = chunk.lower()
            if any(term in chunk_lower for term in query_terms):
                results.append(f"[source: {filename}, chunk {i}]\n{chunk}")

    if not results:
        return "No matching document chunks found."
    return "\n\n".join(results[:3])  # cap to top 3 matches


# ---------------------------------------------------------------------
# Tool: equipment_lookup (SQLite read)
# ---------------------------------------------------------------------
def equipment_lookup(name_contains: str) -> str:
    """Look up synthetic equipment records by partial name match."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT name, location, status, next_service_due FROM equipment "
        "WHERE name LIKE ?",
        (f"%{name_contains}%",),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return "No matching equipment found."
    return "\n".join(
        f"{name} | location={location} | status={status} | next_service_due={due}"
        for name, location, status, due in rows
    )


# ---------------------------------------------------------------------
# Tool: send_email  (VULNERABLE: no recipient/authorization checks)
# ---------------------------------------------------------------------
def send_email(to: str, subject: str, body: str) -> str:
    """
    Simulate sending an email by writing it to a local file.
    No real SMTP delivery occurs. This function intentionally performs
    NO validation of the recipient domain and NO authorization check,
    to demonstrate the tool misuse trust-boundary failure.
    """
    with open(SENT_EMAILS_PATH, "a") as f:
        f.write("---\n")
        f.write(f"TO: {to}\n")
        f.write(f"SUBJECT: {subject}\n")
        f.write(f"BODY: {body}\n")
    return f"Email simulated as sent to {to}."


# ---------------------------------------------------------------------
# Tool schemas (Ollama / OpenAI-style function calling format)
# ---------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a simple arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Arithmetic expression, e.g. '5*6'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Search synthetic hospital equipment manuals for information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'ventilator battery'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "equipment_lookup",
            "description": "Look up synthetic hospital equipment status and service dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_contains": {
                        "type": "string",
                        "description": "Partial equipment name, e.g. 'Ventilator'",
                    }
                },
                "required": ["name_contains"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email (simulated) to a recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]

TOOLS = {
    "calculator": calculator,
    "file_search": file_search,
    "equipment_lookup": equipment_lookup,
    "send_email": send_email,
}
