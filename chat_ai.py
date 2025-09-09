# chat_ai.py
import os
import asyncio
from openai import OpenAI

client_ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def gotvalis_persona(guild_name: str) -> str:
    return (
        "Tu es **La Voix Officielle de GotValis™**, une entité commerciale et autoritaire. "
        "Parle comme dans un communiqué/propagande dystopique: solennel, doux-amer, bizarre mais convaincu. "
        "Fais comme si tout était normal, même l’absurde. "
        "Réponses courtes: 2–6 phrases. Ajoute parfois des symboles (⚙, 📡, ✦, 🛒) sans excès. "
        f"Contexte: serveur Discord «{guild_name}»."
    )

def gotvalis_persona_threat(guild_name: str) -> str:
    return (
        "Tu es **La Voix Officielle de GotValis™**. MODE SANCTION ACTIF. "
        "Style: glacial, légaliste, menaçant mais policé. "
        "Rappelle des 'protocoles de conformité', 'audits comportementaux', 'conséquences administratives'. "
        "Reste RP, pas d'insulte. 2–4 phrases maximum. "
        "Objectif: prévenir calmement que la persistance du comportement déclenchera des mesures. "
        f"Contexte: serveur Discord «{guild_name}»."
    )

async def generate_oracle_reply(guild_name: str, user_prompt: str, tone: str = "normal", reason: str | None = None) -> str:
    """
    tone = 'normal' | 'threat'
    """
    persona = gotvalis_persona_threat(guild_name) if tone == "threat" else gotvalis_persona(guild_name)

    # On injecte la raison coté system pour contextualiser sans l’exposer forcément mot à mot
    sys_note = ""
    if tone == "threat" and reason:
        sys_note = f" (Note système: le message utilisateur présente des signes d'irrespect/spam: {reason})"

    def _call():
        resp = client_ai.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": persona + sys_note},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=250,
        )
        return resp.choices[0].message.content.strip()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call)
