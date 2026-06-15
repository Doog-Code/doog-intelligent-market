import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def translate_lot(items):
    """Traduit un lot de 10 articles maximum."""
    prompt_lines = []
    for i, item in enumerate(items):
        prompt_lines.append(f"[{i+1}] TITRE: {item['title']}")
        prompt_lines.append(f"[{i+1}] RESUME: {item['summary'][:200]}")

    prompt = "\n".join(prompt_lines)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """Traduis en français. Conserve exactement le format:
[N] TITRE: texte traduit
[N] RESUME: texte traduit
Rien d'autre. Garde tickers, chiffres et noms propres intacts."""
            },
            {
                "role": "user",
                "content": f"Traduis:\n\n{prompt}"
            }
        ],
        max_tokens=1500,
        temperature=0.1
    )

    result   = response.choices[0].message.content.strip()
    translated = [item.copy() for item in items]

    for line in result.split("\n"):
        line = line.strip()
        if not line:
            continue
        for i in range(len(items)):
            n = i + 1
            for sep in [":", " :"]:
                if line.startswith(f"[{n}] TITRE{sep}"):
                    translated[i]["title"] = line.split(sep, 1)[-1].strip()
                if line.startswith(f"[{n}] RESUME{sep}"):
                    translated[i]["summary"] = line.split(sep, 1)[-1].strip()

    return translated

def translate_batch(items, lot_size=8):
    """Traduit tous les articles par lots."""
    if not items:
        return items

    all_translated = []
    for i in range(0, len(items), lot_size):
        lot = items[i:i+lot_size]
        try:
            translated = translate_lot(lot)
            all_translated.extend(translated)
            print(f"    ✓ Lot {i//lot_size + 1} traduit ({len(lot)} articles)")
        except Exception as e:
            print(f"    ⚠ Lot {i//lot_size + 1} échoué ({e}) — conservé en anglais")
            all_translated.extend(lot)

    return all_translated
