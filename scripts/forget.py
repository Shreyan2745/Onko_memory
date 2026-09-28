"""
Remove unwanted memories (test messages, typos) from a patient's Hindsight bank.

    python -m scripts.forget "kesa hai"                 # search Rajesh's bank, confirm, delete
    python -m scripts.forget "kesa hai" --patient 2     # another patient id
    python -m scripts.forget "kesa hai" --yes           # skip the confirmation

How it works: every save (retain) is stored as a Hindsight *document*; the facts
extracted from it point back to that document. Deleting the document removes the
original text and all facts made from it. Patterns (observations) that used it are
re-consolidated by Hindsight in the background.
Only this app's bank for the current HINDSIGHT_BANK_PREFIX is touched.
"""

from __future__ import annotations

import asyncio
import sys

from core import config, memory


def _run(coro):
    """Run a coroutine on memory's Hindsight thread (same loop as every other call)."""
    return asyncio.run_coroutine_threadsafe(coro, memory._loop).result(timeout=120)


def find_matches(bank_id: str, text: str) -> dict[str, list[str]]:
    """{document_id: [matching memory texts]} for memories containing `text`."""
    matches: dict[str, list[str]] = {}
    offset = 0
    while True:
        page = memory._call("alist_memories", bank_id=bank_id, search_query=text, limit=100, offset=offset)
        items = getattr(page, "items", None) or []
        for item in items:
            doc_id = getattr(item, "document_id", None)
            if doc_id:
                matches.setdefault(doc_id, []).append(item.text)
        if len(items) < 100:
            return matches
        offset += 100


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit('Usage: python -m scripts.forget "text to search for" [--patient ID] [--yes]')
    text = args[0]
    patient_id = int(sys.argv[sys.argv.index("--patient") + 1]) if "--patient" in sys.argv else 1
    if not memory.is_online():
        sys.exit("Hindsight is offline. Run: python -m scripts.check_setup")

    bank_id = memory.bank_id_for(patient_id)
    matches = find_matches(bank_id, text)
    if not matches:
        print(f"Nothing in '{bank_id}' matches {text!r}.")
        return

    print(f"Found {len(matches)} saved item(s) in '{bank_id}' matching {text!r}:\n")
    for i, (doc_id, texts) in enumerate(matches.items(), 1):
        print(f"  {i}. document {doc_id}")
        for t in texts[:3]:
            print(f"       - {t[:110]}")
    if "--yes" not in sys.argv and input("\nDelete all of these? Type yes: ").strip().lower() != "yes":
        print("Cancelled. Nothing was deleted.")
        return

    client = memory._get_client()
    for doc_id in matches:
        _run(client.documents.delete_document(bank_id=bank_id, document_id=doc_id))
        print(f"  deleted {doc_id}")
    print(f"\nDone. Refresh the app page to clear the chat on screen (prefix: {config.HINDSIGHT_BANK_PREFIX}).")


if __name__ == "__main__":
    main()
