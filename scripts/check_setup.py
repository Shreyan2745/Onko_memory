"""
Hour-0 check: are Hindsight and Groq working?   python -m scripts.check_setup
Uses a throwaway bank "<prefix>-setup-check".
"""

from core import config, memory
from core.contracts import Patient


def main() -> None:
    print("── Hindsight ──")
    if not memory.is_online():
        print("✗ Not configured. Set HINDSIGHT_BASE_URL (and HINDSIGHT_API_KEY for Cloud) in .env")
    else:
        bank = f"{config.HINDSIGHT_BANK_PREFIX}-setup-check"
        memory._call("aretain", bank_id=bank, content="Setup check: the team name is 404 Found.", retain_async=False)
        print("✓ retain ok")
        print("✓ reflect:", memory._call("areflect", bank_id=bank, query="What is the team name?", budget="low").text)
        bank_id = memory.ensure_bank(Patient(id=0, name="Setup Check"))
        resp = memory._call("alist_directives", bank_id=bank_id)
        found = {d.name for d in (getattr(resp, "items", None) or resp or [])}
        missing = set(memory.DIRECTIVES) - found
        if missing:
            print(f"✗ directives missing on {bank_id}: {sorted(missing)}")
        else:
            print(f"✓ bank + all {len(memory.DIRECTIVES)} directives present ({bank_id})")

    print("── Groq ──")
    if not config.GROQ_API_KEY:
        print("✗ GROQ_API_KEY missing in .env")
    else:
        from core.ai.llm import chat_json
        print("✓", chat_json("Reply with JSON.", 'Return {"ok": true}'))


if __name__ == "__main__":
    main()