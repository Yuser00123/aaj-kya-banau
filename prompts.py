"""
prompts.py — the AI half of Aaj Kya Banau, and its deterministic stand-in.

The matcher (kitchen.py) has ALREADY chosen tonight's recipes. Gemma's job is deliberately
narrow: parse the messy free-text "और क्या है?" box onto the ingredient vocabulary, and write
the MOOD — a short Hinglish verdict, a one-line pitch and a one-line chef tip per recipe, and
the shopping line. It cannot add recipes, cannot invent ingredients, cannot make health claims;
the response is clamped to the recipe IDs and ingredient IDs we sent. The mock makes the whole
app run with zero network, and doubles as the fallback when the model is down.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Set

import kitchen as K
import recipes as RC

SYSTEM = """You are the mood engine of "Aaj Kya Banau?", a sloth-themed dinner decider for Indian kitchens.
The app's matcher has ALREADY chosen tonight's recipes from what is in the kitchen. You never choose,
add or rename recipes.

Return ONLY a JSON object with exactly these keys:
{"verdict": "...", "recipes": [{"id": "...", "pitch": "...", "tip": "..."}], "parsed_extras": ["..."], "shopping_line": "..."}

Rules:
1. LANGUAGE: Hinglish — Roman-script Hindi mixed with English, the way friends talk on WhatsApp
   ("aaj bas 15 minute ka kaam hai"). Warm, lazy, a little funny. No Devanagari in your output.
2. VERDICT: 2-3 lines naming tonight's pick and why — use ONLY the given facts: how many items are
   missing, the effort score, the minutes, what is in the kitchen.
3. RECIPES: one entry for EACH recipe given, with the SAME id. pitch = one line selling it for
   tonight; tip = one practical cooking tip that uses ONLY that recipe's given ingredients/steps.
   No nutrition or health claims. No new ingredients.
4. PARSED_EXTRAS: map the user's free-text notes onto the ingredient vocabulary given (ids only).
   Ignore anything that is not in the vocabulary. If the free text is empty, return [].
5. SHOPPING_LINE: one line about what to buy (from the missing items), or a lazy celebration line
   if nothing is missing.
6. No markdown, no emojis, no invented dishes, no prices."""

# Hinglish mood for the days the model is unreachable — the dinner still gets decided.


def _kitchen_summary(have: Set[str]) -> str:
    by_group: Dict[str, List[str]] = {g: [] for g, _ in K.GROUPS}
    for i in have:
        by_group[K.INGREDIENTS[i]["group"]].append(K.label(i))
    return "; ".join(f"{dict(K.GROUPS)[g]}: {', '.join(v) if v else '—'}" for g, v in by_group.items())


def dinner_prompt(m: dict, have: Set[str], sloth_label: str, servings: str, extras_text: str) -> List[dict]:
    top = m["top"]
    payload = [
        {"id": r["id"], "name": r["name"], "effort_of_5": r["effort"], "minutes": r["minutes"],
         "missing": [K.label(i) for i in r["missing"]], "have_optional": [K.label(i) for i in r["opt"] if i in have]}
        for r in top
    ]
    one_away = [{"id": r["id"], "name": r["name"], "minutes": r["minutes"],
                 "would_need": [K.label(i) for i in r["missing"]]} for r in m["one_away"]]
    user = (
        "MATTER_ID: dinner\n\n"
        f"USER'S KITCHEN: {_kitchen_summary(have)}\n"
        f"HOW LAZY TODAY: {sloth_label} · SERVINGS: {servings}\n"
        f"FREE TEXT from user (parse onto the vocabulary; ignore what is not in it): {extras_text.strip() or '(none)'}\n\n"
        f"MATCHED RECIPES (tonight's shortlist, best first — write pitch/tip for EACH):\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n"
        f"ONE-ITEM-AWAY (mention at most in shopping_line if useful):\n{json.dumps(one_away, ensure_ascii=False, indent=1)}\n\n"
        f"INGREDIENT VOCABULARY (ids for parsed_extras): {json.dumps(sorted(K.INGREDIENTS), ensure_ascii=False)}\n\n"
        "Write the JSON object now."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def mock_draft(m: dict, have: Set[str], sloth_label: str, servings: str, extras_text: str) -> dict:
    top = m["top"]
    if not top:
        return {"verdict": "(mock) Rasoi kaafi khali hai — kuch khaas nahi ban sakta. Model connect karo to Gemma suggestion dega.",
                "recipes": [], "parsed_extras": sorted(K.parse_extras(extras_text)), "shopping_line": ""}
    best = top[0]
    n_missing = len(best["missing"])
    verb = "sab kuch ghar pe hai" if not n_missing else f"bas {best['missing'][0]} lana padega" if n_missing == 1 else f"{n_missing} cheezein kami hain"
    return {
        "verdict": f"(mock) Aaj ka dinner: {best['name']} — {best['minutes']} minute, {verb}. "
                   f"Model juda to Gemma poora mood likhega; abhi bhi dinner decide ho gaya.",
        "recipes": [{"id": r["id"], "pitch": r["pitch"], "tip": r["tip"]} for r in top],
        "parsed_extras": sorted(K.parse_extras(extras_text)),
        "shopping_line": "Kuch nahi lana padega — jo hai usi mein banega." if not any(r["missing"] for r in top) else "Missing cheezein upar list mein hain.",
    }


def mock_reply(messages: List[dict], json_mode: bool) -> str:
    """Registered as llm.MOCK_HANDLER — deterministic, no network."""
    user = next((x["content"] for x in reversed(messages) if x["role"] == "user"), "")
    return json.dumps({"verdict": "(mock) Dinner decide ho gaya — Gemini/Gemma juda to poora mood bhi aayega.",
                       "recipes": [], "parsed_extras": [], "shopping_line": ""}, ensure_ascii=False)


def _s(x) -> str:
    return str(x or "").strip()


def validate_draft(d, m: dict, have: Set[str], extras_text: str) -> dict:
    """Clamp the model's JSON: only our recipe ids, only our ingredient ids; fill gaps from the DB."""
    mock = mock_draft(m, have, "", "", extras_text)
    if not isinstance(d, dict):
        return mock
    by_id = {r["id"]: r for r in m["top"]}
    pitches = {}
    raw = d.get("recipes")
    if isinstance(raw, list):
        for e in raw:
            if isinstance(e, dict) and e.get("id") in by_id:
                pitches[e["id"]] = (_s(e.get("pitch")) or by_id[e["id"]]["pitch"], _s(e.get("tip")) or by_id[e["id"]]["tip"])
    if not pitches:
        pitches = {r["id"]: (r["pitch"], r["tip"]) for r in m["top"]}
    extras = d.get("parsed_extras")
    extras = sorted({x for x in extras if x in K.INGREDIENTS}) if isinstance(extras, list) else sorted(K.parse_extras(extras_text))
    return {
        "verdict": _s(d.get("verdict")) or mock["verdict"],
        "recipes": [{"id": rid, "pitch": p, "tip": t} for rid, (p, t) in pitches.items()],
        "parsed_extras": extras,
        "shopping_line": _s(d.get("shopping_line")) or mock["shopping_line"],
    }


def draft_dinner(m: dict, have: Set[str], sloth_label: str, servings: str, extras_text: str) -> dict:
    """Call the model, clamp its output."""
    import llm

    raw = llm.chat(dinner_prompt(m, have, sloth_label, servings, extras_text), json_mode=True, max_tokens=2500, budget=90)
    return validate_draft(llm.parse_json(raw), m, have, extras_text)
