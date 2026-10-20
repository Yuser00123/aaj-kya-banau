"""
आज क्या बनाऊँ? (Aaj Kya Banau?) — a sloth decides dinner from what's already in the kitchen.

The 6 PM question, answered by code instead of a tired brain: tick your kitchen once (the browser
remembers), pick how lazy you feel, and the deterministic matcher names tonight's top 3 from a
40-recipe open database — ranked by fewest missing items and least effort. Gemma 4 writes only the
mood: the verdict, a one-line pitch and a chef tip per dish, and parses your messy free-text
("thoda basi chawal, aadha gobhi") onto the ingredient vocabulary. It never chooses recipes and
never invents ingredients. Model down? Dinner still gets decided (mock mode, zero network).

Hacktoberfest 2026 · Week 3: Slow and Steady · https://github.com/Yuser00123/aaj-kya-banau
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Set

_env = Path(__file__).with_name(".env")  # tiny .env loader (no python-dotenv dependency)
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import gradio as gr  # noqa: E402
from fastapi import FastAPI  # noqa: E402

import kitchen as K  # noqa: E402
import llm  # noqa: E402
import prompts as P  # noqa: E402
import recipes as RC  # noqa: E402

llm.MOCK_HANDLER = P.mock_reply
REPO_URL = os.getenv("REPO_URL", "https://github.com/Yuser00123/aaj-kya-banau")
STARTED = time.time()
SLOTH_LABEL = {sid: lbl for sid, lbl, _ in K.SLOTH_LEVELS}
MEDALS = ["🥇", "🥈", "🥉"]


# ----------------------------------------------------------------------------- rendering
def _missing_line(r: dict) -> str:
    if not r["missing"]:
        return "✅ घर में सब कुछ मौजूद — कुछ लाना नहीं पड़ेगा"
    names = ", ".join(K.label(i) for i in r["missing"])
    return f"🛒 बस ये ले आना होगा: **{names}**"


def render_cards(m: dict, draft: dict) -> str:
    candidates = m["top"] or m["one_away"][:3] or m["far"][:3]
    if not candidates:
        return ("## 😅 इस रसोई में अभी कुछ नहीं बनता\n\n"
                "ऊपर से कुछ चीज़ें टिक करो — या ये **स्टार्टर किट** ले आओ, फिर दोबारा बटन दबाओ:\n\n"
                + "\n".join(f"☐ {K.label(i)}" for i in K.STARTER_KIT))
    pitch_by_id = {r["id"]: r for r in draft.get("recipes", [])}
    L = []
    if not m["top"]:
        L.append("### 🛒 एक-दो चीज़ लेकर आओ — फिर ये बन जाएगा:\n")
    for idx, r in enumerate(candidates[:3]):
        p = pitch_by_id.get(r["id"], {})
        L.append(f"## {MEDALS[idx]} {r['emoji']} {r['name']} — {r['minutes']} मिनट · {'🦥' * r['effort']}")
        L.append(f"*{p.get('pitch') or r['pitch']}*")
        L.append(_missing_line(r))
        L.append(f"💡 *{p.get('tip') or r['tip']}*")
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(r["steps"], 1))
        L.append(f"<details><summary>👨‍🍳 बनाने का तरीका ({len(r['steps'])} स्टेप)</summary>\n\n{steps}\n\n</details>")
        L.append("")
    return "\n".join(L)


def render_alt(m: dict) -> str:
    rows = []
    if m["one_away"]:
        rows.append("**🥔 एक चीज़ ले आओ (बस एक!):**\n")
        rows.append("| विकल्प | समय | मेहनत | लाना होगा |")
        rows.append("|---|---|---|---|")
        for r in m["one_away"]:
            rows.append(f"| {r['emoji']} {r['name']} | {r['minutes']} मिनट | {'🦥' * r['effort']} | {', '.join(K.label(i) for i in r['missing'])} |")
        rows.append("")
    if m["rest"]:
        rows.append(f"**🌙 और भी बन सकता है (आज {m['n_possible']} विकल्प बन सकते हैं):** "
                    + ", ".join(f"{r['name']} ({r['minutes']} मिनट)" for r in m["rest"]))
    if m["relaxed"]:
        rows.append("\n⚠️ *आज की मेहनत-सीमा में कुछ नहीं मिला — ऊपर वालों में से एक चुन लो, या थोड़ी मेहनत मान लो।*")
    return "\n".join(rows) or "*सब कुछ ऊपर ही है — और क्या चाहिए?* 🦥"


def _collect(*groups) -> Set[str]:
    have: Set[str] = set()
    for g in groups:
        have |= {i for i in (g or []) if i in K.INGREDIENTS}
    return have


def generate(g_staples, g_sabzi, g_dairy, g_masala, extras_text, sloth, servings, veg_only, store):
    """Kitchen ticks -> (status, cards, alternatives, shopping list, saved kitchen)."""
    have = _collect(g_staples, g_sabzi, g_dairy, g_masala) | K.parse_extras(extras_text or "")
    sloth = sloth or "thodi"
    m = K.match(have, sloth, bool(veg_only), RC.RECIPES)

    if m["top"] and llm.available():
        yield (f"⏳ Gemma aaj ka mood likh raha hai… (आमतौर पर 20–60 सेकंड)", gr.update(), gr.update(), gr.update(), gr.update())
        draft = None
        note = ""
        try:
            draft = P.draft_dinner(m, have, SLOTH_LABEL[sloth], servings or "1-2 लोग", extras_text or "")
        except Exception as err:  # noqa: BLE001 — dinner must still be decided
            note = f"⚠️ मॉडल से नहीं लिख पाए ({err}) — डेटाबेस वाली पिच दिखा रहे हैं। "
    else:
        draft, note = None, ""

    if draft is None:
        draft = P.mock_draft(m, have, SLOTH_LABEL[sloth], servings or "", extras_text or "")

    new_items = [i for i in draft.get("parsed_extras", []) if i not in have and i in K.INGREDIENTS]
    if new_items:
        have |= set(new_items)
        note += "🧠 तुमने लिखा था — समझ लिया: " + ", ".join(K.label(i) for i in new_items) + ". "

    if m["relaxed"]:
        note += "🦥 आज की मेहनत-सीमा में कुछ नहीं था, थोड़ा ऊपर देखना पड़ेगा। "

    yield (
        note + (draft.get("verdict") or ""),
        render_cards(m, draft),
        render_alt(m),
        K.shopping_text(m),
        {"have": sorted(have), "extras_text": extras_text or ""},
    )


def restore(store):
    store = store or {}
    have = {i for i in store.get("have", []) if i in K.INGREDIENTS}
    vals = {g: [i for i in have if K.INGREDIENTS[i]["group"] == g] for g, _ in K.GROUPS}
    return vals["staples"], vals["sabzi"], vals["dairy"], vals["masala"], store.get("extras_text", "")


def clear_kitchen():
    return [], [], [], [], "", {"have": [], "extras_text": ""}


# ----------------------------------------------------------------------------- UI
CSS = """
.gradio-container { max-width: 860px !important; margin: auto; }
#title h1 { font-size: 1.7rem; margin-bottom: 0; }
#cards { font-size: 1.02rem; line-height: 1.55; }
#cards h2 { margin-top: 1.2rem; }
#cards details { background: #f8f7f2; border: 1px solid #e3e0d5; border-radius: 8px; padding: 6px 12px; }
button.lg { min-height: 52px; font-size: 1.05rem; }
@media print {
  body * { visibility: hidden; }
  #cards, #cards *, #shopping, #shopping * { visibility: visible; }
  #cards { position: absolute; left: 0; top: 0; width: 100%; }
  details { display: block !important; }
}
"""
COPY_JS = """async (txt) => {
  try { await navigator.clipboard.writeText(txt); alert('कॉपी हो गया ✓'); }
  catch (e) { alert('कॉपी नहीं हुआ — टेक्स्ट खुद सिलेक्ट करके कॉपी करें'); }
  return txt;
}"""

with gr.Blocks(title="आज क्या बनाऊँ?") as demo:
    store = gr.BrowserState({"have": [], "extras_text": ""}, storage_key="aaj-kya-banau-v1")
    gr.Markdown(
        "# 🦥 आज क्या बनाऊँ?\n"
        "**रसोई में जो है, उसी से रात का खाना तय करो — 6 बजे वाला सवाल अब ऐप की ज़िम्मेदारी है।**\n"
        "किचन टिक करो (एक बार — ब्राउज़र याद रखता है) · बताओ कितनी मेहनत होगी · बटन दबाओ। "
        "रेसिपी, मैचिंग और स्टेप्स **कोड** से आते हैं (40 रेसिपी का खुला डेटाबेस); **Gemma** सिर्फ़ मूड लिखता है "
        "और तुम्हारी इधर-उधर लिखी बात समझता है — कोई नई रेसिपी गढ़ता नहीं।",
        elem_id="title",
    )
    gr.Markdown("**कैसे:** ① जो घर में है वो टिक करो → ② 🦥 बताओ दबाओ → ③ पहला कार्ड ही आज का खाना है। बस।", elem_id="howto")

    with gr.Tab("🦥 बताओ"):
        with gr.Group():
            cb_groups = []
            for gid, glabel in K.GROUPS:
                cb_groups.append(gr.CheckboxGroup(choices=K.choices(gid), label=glabel))
            extras_tb = gr.Textbox(
                label="और क्या है? (अपनी भाषा में — जैसे: thoda basi chawal, aadha gobhi, ek anda)",
                placeholder="जो ऊपर टिक नहीं हो सका, यहाँ लिख दो — समझ लिया जाएगा", lines=2)
            with gr.Row():
                sloth_rd = gr.Radio(choices=[(lbl, sid) for sid, lbl, _ in K.SLOTH_LEVELS], value="kam",
                                    label="आज कितनी मेहनत?", scale=2)
                servings_rd = gr.Radio(choices=K.SERVINGS, value="1-2 लोग", label="कितने लोग?", scale=1)
            veg_cb = gr.Checkbox(value=True, label="सिर्फ़ वेज (अंडा-चिकन हटा दो)")
        go_btn = gr.Button("🦥 बताओ — आज क्या बनाऊँ?", variant="primary", elem_classes=["lg"])

        status_md = gr.Markdown()
        cards_md = gr.Markdown(elem_id="cards")
        with gr.Accordion("🥔 बाक़ी विकल्प — एक चीज़ ले आओ", open=False):
            alt_md = gr.Markdown()
        with gr.Accordion("🛒 खरीद की लिस्ट", open=True):
            with gr.Row():
                shop_tb = gr.Textbox(label="जो लाना हो तो", lines=4, elem_id="shopping", scale=4)
                copy_btn = gr.Button("📋 कॉपी", scale=1)
        clear_btn = gr.Button("🗑 रसोई खाली करो (नई शुरुआत)")

    gr.Markdown(
        f"<small>नमक-तेल-हल्दी जैसे बुनियादी मसाले मान लिए गए हैं (रेसिपी में 'वैकल्पिक')। पोषण के दावे नहीं — "
        f"बस घर का खाना। तुम्हारी रसोई की लिस्ट **सिर्फ़ इस ब्राउज़र** में रहती है। रेसिपी डेटाबेस "
        f"(<a href='{REPO_URL}'>recipes.py</a>) खुला है — अपनी घरेलू रेसिपी ~8 लाइनों में जोड़ सकते हो। "
        f"Model: **{llm.describe()}** · Hacktoberfest 2026 · Week 3: Slow and Steady</small>"
    )

    go_btn.click(generate, inputs=[*cb_groups, extras_tb, sloth_rd, servings_rd, veg_cb, store],
                 outputs=[status_md, cards_md, alt_md, shop_tb, store])
    copy_btn.click(None, inputs=[shop_tb], outputs=[shop_tb], js=COPY_JS)
    clear_btn.click(clear_kitchen, outputs=[*cb_groups, extras_tb, store])
    demo.load(restore, inputs=[store], outputs=[*cb_groups, extras_tb])

api = FastAPI(title="Aaj Kya Banau")


@api.get("/health")
def health():
    return {
        "status": "ok", "service": "aaj-kya-banau", "model": llm.describe(),
        "recipes": len(RC.RECIPES), "ingredients": len(K.INGREDIENTS),
        "uptime_seconds": int(time.time() - STARTED), "version": "1.0.0",
    }


app = gr.mount_gradio_app(api, demo, path="/", theme=gr.themes.Soft(primary_hue="emerald", secondary_hue="amber"), css=CSS, pwa=True)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
