"""
Offline test suite for आज क्या बनाऊँ? — no network, no LLM key, no browser.

Run:  python3 test_app.py   (or pytest test_app.py)
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LLM_PROVIDER", "mock")

import kitchen as K  # noqa: E402
import prompts as P  # noqa: E402
import recipes as RC  # noqa: E402

ALL = set(K.INGREDIENTS)
PASSED = []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        sys.exit(1)


print("1. vocab + recipes import cleanly (verify() runs on import)")
check("40 recipes", len(RC.RECIPES) == 40, f"got {len(RC.RECIPES)}")
check("52 ingredients", len(K.INGREDIENTS) == 52, f"got {len(K.INGREDIENTS)}")
check("starter kit ids valid", all(i in K.INGREDIENTS for i in K.STARTER_KIT))
check("all recipes veg-flagged", all(isinstance(r["veg"], bool) for r in RC.RECIPES))

print("2. matcher: full kitchen, lazy, veg")
m = K.match(ALL, "kam", True, RC.RECIPES)
check("top3 all zero-missing", all(not r["missing"] for r in m["top"]))
check("laziest first (dahi_chawal)", m["top"][0]["id"] == "dahi_chawal", m["top"][0]["id"])
check("rest present", isinstance(m.get("rest"), list) and len(m["rest"]) >= 3)
check("not relaxed", not m["relaxed"])

print("3. matcher: sparse kitchen (sirf maggi)")
m = K.match({"maggi", "namak", "tel", "haldi"}, "kam", True, RC.RECIPES)
check("maggi top-1", m["top"][0]["id"] == "masala_maggi", m["top"][0]["id"])

print("4. matcher: empty kitchen -> only one-away suggestions (ek cheez le aao)")
m = K.match(set(), "thodi", True, RC.RECIPES)
check("top exists but every dish misses something", m["top"] and all(r["missing"] for r in m["top"]))
check("one_away non-empty", len(m["one_away"]) >= 1)
check("n_possible > 0", m["n_possible"] >= 1)

print("5. veg filter")
CHICKEN_KITCHEN = {"chicken", "pyaz", "tamatar", "dahi", "namak", "tel", "haldi"}
m = K.match(CHICKEN_KITCHEN, "pura", False, RC.RECIPES)
ids = [r["id"] for r in m["top"] + m["one_away"] + m["rest"]]
check("chicken visible when non-veg allowed", "chicken_curry" in ids)
m = K.match(CHICKEN_KITCHEN, "pura", True, RC.RECIPES)
ids = [r["id"] for r in m["top"] + m["one_away"] + m["rest"]]
check("no non-veg when veg_only", all(r["veg"] for r in RC.RECIPES if r["id"] in ids), str(ids))

print("6. effort cap + relaxed fallback (synthetic DB: only heavy dishes possible)")
m = K.match(ALL, "kam", False, RC.RECIPES)
check("kam -> top3 effort <= 2", all(r["effort"] <= 2 for r in m["top"]))
HEAVY = [{
    "id": "royal_biryani", "name": "रॉयल बिरयानी", "emoji": "🍛", "req": ["chawal", "aloo"], "opt": [],
    "effort": 5, "minutes": 90, "veg": True, "steps": ["layer", "dum"], "pitch": "shaan", "tip": "dheere pakao",
}]
m = K.match({"chawal", "aloo"}, "kam", True, HEAVY)
check("relaxed when only heavy dishes possible", m["relaxed"] and m["top"][0]["id"] == "royal_biryani")

print("7. recipe DB sanity")
by_id = {r["id"]: r for r in RC.RECIPES}
check("unique ids", len(by_id) == 40)
check("steps non-empty", all(r["steps"] for r in RC.RECIPES))
check("basi chawal recipe exists", "basi_chawal" in by_id["chawal_bhunjna"]["req"])
check("some non-veg recipes exist", any(not r["veg"] for r in RC.RECIPES))

print("8. free-text parsing (deterministic + clamp)")
p = K.parse_extras("thoda basi chawal hai, aadha gobhi bhi")
check("roman alias basi chawal", p == {"basi_chawal", "phool_gobhi"}, str(p))
p = K.parse_extras("patta gobhi bhi hai")
check("patta gobhi stays cabbage", p == {"gobhi"}, str(p))
p = K.parse_extras("प्याज़ और लहसुन भी है")
check("devanagari labels", {"pyaz", "lasun"} <= set(p), str(p))
p = K.parse_extras("truffle aur caviar")
check("unknown ignored", p == set(), str(p))

print("9. prompt + clamp (mock model output)")
have = {"atta", "aloo", "pyaz", "namak", "tel", "haldi"}
m = K.match(have, "kam", True, RC.RECIPES)
msgs = P.dinner_prompt(m, have, "आज बिल्कुल नहीं", "1-2 लोग", "ek anda bhi hai")
check("system+user", len(msgs) == 2 and msgs[0]["role"] == "system")
check("prompt has matched ids", all(r["id"] in msgs[1]["content"] for r in m["top"]))
check("prompt has vocabulary", "phool_gobhi" in msgs[1]["content"])
fake = {"verdict": "", "recipes": [{"id": "pizza_margherita", "pitch": "x"}, {"id": m["top"][0]["id"], "pitch": "", "tip": ""}],
        "parsed_extras": ["truffle", "andaa"], "shopping_line": ""}
v = P.validate_draft(fake, m, have, "ek anda bhi hai")
check("invented recipe dropped, real kept", [r["id"] for r in v["recipes"]] and "pizza_margherita" not in [r["id"] for r in v["recipes"]])
check("real pitch fills empty", v["recipes"][0]["pitch"])
check("invented ingredient dropped", "truffle" not in v["parsed_extras"])
check("andaa kept", "andaa" in v["parsed_extras"])
check("verdict filled from mock", v["verdict"])

print("10. mock draft is self-sufficient")
d = P.mock_draft(m, have, "kam", "1-2 लोग", "")
check("mock verdict mentions pick", m["top"][0]["name"] in d["verdict"])
check("mock pitches for all top", {r["id"] for r in d["recipes"]} == {r["id"] for r in m["top"]})

print("11. shopping text")
check("nothing to buy", "कुछ नहीं लाना पड़ेगा" in K.shopping_text(K.match(ALL, "kam", True, RC.RECIPES)))
m = K.match({"bread"}, "thodi", True, RC.RECIPES)
t = K.shopping_text(m)
check("missing items listed", ("टमाटर" in t or "पनीर" in t) and "☐" in t, t)

print("12. generate() round-trip (mock provider, Gradio-free call)")
import app  # noqa: E402

out = None
for out in app.generate(["atta", "chawal", "arhar_dal"], ["aloo", "pyaz", "tamatar"], ["dahi"], ["namak", "tel", "haldi"],
                        "thoda basi chawal bhi hai", "kam", "1-2 लोग", True, {"have": [], "extras_text": ""}):
    pass
status, cards, alt, shop, store = out
check("cards have a recipe name", any(r["name"] in cards for r in RC.RECIPES))
check("status mentions model or verdict", len(status) > 10)
check("store saved kitchen incl. parsed basi_chawal", "basi_chawal" in store["have"])
check("store saved extras_text", store["extras_text"] == "thoda basi chawal bhi hai")
check("shopping box filled", len(shop) > 0)

print("13. /health endpoint")
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app.api)
r = client.get("/health")
check("health 200", r.status_code == 200)
check("health payload", r.json()["recipes"] == 40 and r.json()["service"] == "aaj-kya-banau")
check("index 200", client.get("/").status_code == 200)

print("14. restore() from BrowserState")
vals = app.restore({"have": ["atta", "aloo", "dahi", "namak"], "extras_text": "hello"})
check("restore groups", vals[0] == ["atta"] and vals[1] == ["aloo"] and vals[2] == ["dahi"] and vals[3] == ["namak"] and vals[4] == "hello")

print(f"\nALL {len(PASSED)} CHECKS PASSED")
