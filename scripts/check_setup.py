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
        c = memory._get_client()  # shared client, closed cleanly on exit
        bank = f"{config.HINDSIGHT_BANK_PREFIX}-setup-check"
        c.retain(bank_id=bank, content="Setup check: the team name is 404 Found.", retain_async=False)
        print("✓ retain ok")
        print("✓ reflect:", c.reflect(bank_id=bank, query="What is the team name?", budget="low").text)
        memory.ensure_bank(Patient(id=0, name="Setup Check"))
        print("✓ bank + directives ok")

    print("── Groq ──")
    if not config.GROQ_API_KEY:
        print("✗ GROQ_API_KEY missing in .env")
    else:
        from core.ai.llm import chat_json
        print("✓", chat_json("Reply with JSON.", 'Return {"ok": true}'))


if __name__ == "__main__":
    main()