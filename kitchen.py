"""
kitchen.py — the deterministic half of Aaj Kya Banau (आज क्या बनाऊँ?).

The ingredient vocabulary (~52 items of an ordinary Indian kitchen) and the matcher that decides
what can actually be cooked TONIGHT from what is ticked. The AI never chooses recipes — this file
does, with plain, editable Python. Add an item or a synonym and the app updates; no vendor ticket.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Set

# ----------------------------------------------------------------------------- vocabulary
INGREDIENTS: Dict[str, dict] = {
    # staples — aata, chawal, dal, nashta
    "atta":        {"label": "आटा", "emoji": "🌾", "group": "staples", "aliases": ["atta", "aata", "flour", "gehu"]},
    "chawal":      {"label": "चावल (कच्चे)", "emoji": "🍚", "group": "staples", "aliases": ["chawal", "chaval", "rice", "caul", "caawal"]},
    "basi_chawal": {"label": "बासी / पके हुए चावल", "emoji": "🍚", "group": "staples", "aliases": ["basi", "pake chawal", "leftover rice", "basi chawal", "pheeke"]},
    "arhar_dal":   {"label": "अरहर (तूअर) दाल", "emoji": "🥣", "group": "staples", "aliases": ["arhar", "toor", "tur dal", "tuvar", "dal"]},
    "moong_dal":   {"label": "मूंग दाल", "emoji": "🥣", "group": "staples", "aliases": ["moong", "mung", "mong dal"]},
    "chana_dal":   {"label": "चना दाल", "emoji": "🥣", "group": "staples", "aliases": ["chana dal", "channa"]},
    "rajma":       {"label": "राजमा (डिब्बाई / भिगी हुई)", "emoji": "🫘", "group": "staples", "aliases": ["rajma", "rajmah", "kidney beans", "lobia"]},
    "chole":       {"label": "छोले (डिब्बाई / भिगे हुए)", "emoji": "🫘", "group": "staples", "aliases": ["chole", "chhole", "chana", "chickpeas", "kabuli"]},
    "maida":       {"label": "मैदा", "emoji": "🌾", "group": "staples", "aliases": ["maida", "refined flour"]},
    "bread":       {"label": "ब्रेड", "emoji": "🍞", "group": "staples", "aliases": ["bread", "paav", "pav", "double roti"]},
    "poha":        {"label": "चावल का पोहा", "emoji": "🍚", "group": "staples", "aliases": ["poha", "pohe", "chiwda"]},
    "sooji":       {"label": "सूजी / रवा", "emoji": "🌾", "group": "staples", "aliases": ["sooji", "suji", "rava", "rawa", "semolina"]},
    "oats":        {"label": "ओट्स", "emoji": "🥣", "group": "staples", "aliases": ["oats", "ote"]},
    "besan":       {"label": "बेसन", "emoji": "🌾", "group": "staples", "aliases": ["besan", "gram flour", "chane ka atta"]},
    "maggi":       {"label": "मैगी / नूडल्स", "emoji": "🍜", "group": "staples", "aliases": ["maggi", "maggy", "noodles", "nudles", "2 minute"]},
    "sabudana":    {"label": "साबूदाना", "emoji": "⚪", "group": "staples", "aliases": ["sabudana", "sago", "tapioca"]},
    "moongfali":   {"label": "मूंगफली (कच्ची/भुनी)", "emoji": "🥜", "group": "staples", "aliases": ["moongfali", "mongfali", "peanut", "groundnut", "nees"]},
    # sabzi
    "aloo":        {"label": "आलू", "emoji": "🥔", "group": "sabzi", "aliases": ["aloo", "alu", "aalu", "potato", "batata"]},
    "pyaz":        {"label": "प्याज़", "emoji": "🧅", "group": "sabzi", "aliases": ["pyaz", "pyaaj", "onion", "kanda"]},
    "tamatar":     {"label": "टमाटर", "emoji": "🍅", "group": "sabzi", "aliases": ["tamatar", "tamaatar", "tomato"]},
    "lasun":       {"label": "लहसुन", "emoji": "🧄", "group": "sabzi", "aliases": ["lasun", "lasan", "garlic"]},
    "adrak":       {"label": "अदरक", "emoji": "🫚", "group": "sabzi", "aliases": ["adrak", "adarak", "ginger", "sonth"]},
    "hari_mirch":  {"label": "हरी मिर्च", "emoji": "🌶️", "group": "sabzi", "aliases": ["hari mirch", "mirchi", "green chilli", "chili"]},
    "dhaniya":     {"label": "हरा धनिया", "emoji": "🌿", "group": "sabzi", "aliases": ["dhaniya", "coriander", "cilantro", "kothmir"]},
    "gobhi":       {"label": "पत्ता गोभी", "emoji": "🥬", "group": "sabzi", "aliases": ["patta gobhi", "band gobhi", "bandh gobhi", "cabbage", "gobhi patta"]},
    "phool_gobhi": {"label": "फूलगोभी", "emoji": "🥦", "group": "sabzi", "aliases": ["gobhi", "gobi", "phool gobhi", "phoolgobhi", "cauliflower", "gobhi phool"]},
    "bhindi":      {"label": "भिंडी", "emoji": "🌿", "group": "sabzi", "aliases": ["bhindi", "bhendi", "okra", "ladies finger", "lady finger"]},
    "baingan":     {"label": "बैंगन", "emoji": "🍆", "group": "sabzi", "aliases": ["baingan", "bengan", "brinjal", "eggplant", "vangi"]},
    "shimla":      {"label": "शिमला मिर्च", "emoji": "🫑", "group": "sabzi", "aliases": ["shimla", "capsicum", "bell pepper", "simla"]},
    "gajar":       {"label": "गाजर", "emoji": "🥕", "group": "sabzi", "aliases": ["gajar", "carrot"]},
    "matar":       {"label": "मटर", "emoji": "🫛", "group": "sabzi", "aliases": ["matar", "mutter", "peas", "green peas"]},
    "palak":       {"label": "पालक", "emoji": "🥬", "group": "sabzi", "aliases": ["palak", "spinach", "saag"]},
    "lauki":       {"label": "लौकी / घीया", "emoji": "🥒", "group": "sabzi", "aliases": ["lauki", "ghiya", "bottle gourd", "ghia"]},
    "kheera":      {"label": "खीरा", "emoji": "🥒", "group": "sabzi", "aliases": ["kheera", "khira", "cucumber"]},
    "nimbu":       {"label": "नींबू", "emoji": "🍋", "group": "sabzi", "aliases": ["nimbu", "lemon", "lime"]},
    # dairy / egg / meat
    "doodh":       {"label": "दूध", "emoji": "🥛", "group": "dairy", "aliases": ["doodh", "milk", "dudh"]},
    "dahi":        {"label": "दही", "emoji": "🥣", "group": "dairy", "aliases": ["dahi", "curd", "yogurt", "dahee"]},
    "paneer":      {"label": "पनीर", "emoji": "🧈", "group": "dairy", "aliases": ["paneer", "panir", "cottage cheese"]},
    "andaa":       {"label": "अंडा", "emoji": "🥚", "group": "dairy", "aliases": ["anda", "andaa", "egg", "eggs", "ande"]},
    "ghee":        {"label": "घी / मक्खन", "emoji": "🧈", "group": "dairy", "aliases": ["ghee", "makhan", "butter", "amul"]},
    "chicken":     {"label": "चिकन", "emoji": "🍗", "group": "dairy", "aliases": ["chicken", "murgi", "murghi"]},
    # masale & baaki
    "tel":         {"label": "तेल", "emoji": "🫗", "group": "masala", "aliases": ["tel", "oil"]},
    "namak":       {"label": "नमक", "emoji": "🧂", "group": "masala", "aliases": ["namak", "salt"]},
    "haldi":       {"label": "हल्दी", "emoji": "🟡", "group": "masala", "aliases": ["haldi", "turmeric"]},
    "lal_mirch":   {"label": "लाल मिर्च पाउडर", "emoji": "🌶️", "group": "masala", "aliases": ["lal mirch", "red chilli", "kuti mirch"]},
    "dhaniya_p":   {"label": "धनिया पाउडर", "emoji": "🟤", "group": "masala", "aliases": ["dhaniya powder", "coriander powder"]},
    "garam":       {"label": "गरम मसाला", "emoji": "🟤", "group": "masala", "aliases": ["garam masala", "garam"]},
    "jeera":       {"label": "जीरा", "emoji": "🌱", "group": "masala", "aliases": ["jeera", "cumin"]},
    "rai":         {"label": "सरसों / राई", "emoji": "🌱", "group": "masala", "aliases": ["rai", "sarson", "mustard"]},
    "cheeni":      {"label": "चीनी", "emoji": "🍬", "group": "masala", "aliases": ["cheeni", "chini", "sugar", "shakkar"]},
    "sauce":       {"label": "टमाटर सॉस / चिली सॉस", "emoji": "🥫", "group": "masala", "aliases": ["sauce", "ketchup", "ketcup", "chutney"]},
    "chai_patti":  {"label": "चाय पत्ती", "emoji": "🍃", "group": "masala", "aliases": ["chai", "chai patti", "tea", "tea bag", "dip"]},
}

GROUPS = [
    ("staples", "🌾 आटा · चावल · दाल · नाश्ता सामान"),
    ("sabzi", "🥔 सब्ज़ी · फल"),
    ("dairy", "🥛 डेयरी · अंडा · चिकन"),
    ("masala", "🧂 मसाले · बाक़ी"),
]

# how lazy are you today? (maps to the maximum effort score that counts as "fits")
SLOTH_LEVELS = [
    ("kam", "🦥 बिल्कुल नहीं — 20 मिनट से कम", 2),
    ("thodi", "🦥🦥 थोड़ी — 40 मिनट तक", 3),
    ("pura", "🦥🦥🦥 पूरा खाना — जो भी बने", 5),
]
SERVINGS = ["1-2 लोग", "3-4 लोग", "5+ लोग"]

# the universal starter kit — shown when the kitchen is empty
STARTER_KIT = ["atta", "chawal", "arhar_dal", "pyaz", "tamatar", "aloo", "tel", "namak", "haldi", "lal_mirch"]


def label(iid: str) -> str:
    d = INGREDIENTS.get(iid)
    return f"{d['emoji']} {d['label']}" if d else iid


def choices(group: str) -> List[tuple]:
    return [(label(i), i) for i, d in INGREDIENTS.items() if d["group"] == group]


def parse_extras(text: str) -> Set[str]:
    """Deterministic first pass over the free-text 'और क्या है?' box: match Hindi labels and
    Roman aliases, longest name first, and consume the matched text so a shorter name inside a
    longer one (basi CHAWAL, lal MIRCH, patta GOBHI) can't double-fire. Gemma handles the truly
    messy ones; this needs no network."""
    t = " " + (text or "").lower() + " "
    pairs = sorted(((name.lower(), iid) for iid, d in INGREDIENTS.items()
                    for name in [d["label"]] + d["aliases"]), key=lambda p: -len(p[0]))
    found: Set[str] = set()
    for name, iid in pairs:
        if name in t:
            found.add(iid)
            t = t.replace(name, " ")  # consumed — "basi chawal" no longer also matches "chawal"
    return found


# ----------------------------------------------------------------------------- matcher
def match(have: Iterable[str], sloth: str, veg_only: bool, recipes: list) -> dict:
    """What can actually be cooked tonight? Ranked: fewest missing items -> laziest -> fastest.
    'one_away' = recipes that need exactly one thing from the shop ('एक चीज़ ले आओ')."""
    have = {i for i in have if i in INGREDIENTS}
    max_effort = dict((s[0], s[2]) for s in SLOTH_LEVELS).get(sloth, 5)
    perfect, near, far = [], [], []
    for r in recipes:
        if veg_only and not r["veg"]:
            continue
        missing = [i for i in r["req"] if i not in have]
        e = dict(r, missing=missing)
        if not missing:
            perfect.append(e)
        elif len(missing) == 1:
            near.append(e)
        elif len(missing) == 2:
            far.append(e)

    def key(e):
        return (len(e["missing"]), 0 if e["effort"] <= max_effort else 1, e["effort"], e["minutes"])

    pool = sorted(perfect + near, key=key)
    fits = [e for e in pool if e["effort"] <= max_effort] or pool  # relax the sloth bar if nothing fits
    top_ids = {e["id"] for e in fits[:3]}
    one_away = [e for e in near if e["id"] not in top_ids][:4]
    rest = [e for e in perfect if e["id"] not in top_ids][:6]  # possible tonight, just not top-3
    return {
        "top": fits[:3],
        "one_away": one_away,
        "rest": rest,
        "far": sorted(far, key=key)[:4] if not fits else [],
        "relaxed": bool(pool) and not [e for e in pool if e["effort"] <= max_effort],
        "n_possible": len(perfect) + len(near),
    }


def shopping_text(m: dict) -> str:
    """Copyable shopping list from what the top picks are missing."""
    items: List[str] = []
    for e in m["top"] + m["one_away"]:
        for i in e["missing"]:
            if label(i) not in items:
                items.append(label(i))
    if not items:
        return "कुछ नहीं लाना पड़ेगा — जो है उसी में बन जाएगा! 🦥"
    return "खरीद लाओ:\n" + "\n".join(f"☐ {x}" for x in items)


def verify() -> None:
    assert len(INGREDIENTS) >= 50
    assert {d["group"] for d in INGREDIENTS.values()} == {g for g, _ in GROUPS}
    assert all(d["aliases"] for d in INGREDIENTS.values())
    assert parse_extras("thoda basi chawal aur aadha gobhi hai") >= {"basi_chawal"}
    assert "aloo" in parse_extras("AALU bhi hai") or "aloo" in parse_extras("aloo bhi hai")
