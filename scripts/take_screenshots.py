"""Screenshots for the README/DEV post: python3 scripts/take_screenshots.py <url> <outdir>

Drives the app through the real journey on a phone-sized browser:
kitchen ticking -> free text + laziness -> Gemma thinking -> tonight's cards -> shopping list.

Gradio 6 checkboxes are native inputs, so no dropdown warm-up dance is needed (that quirk was
Week 2's dropdown-specific problem). Option labels are clicked via their <label> wrapper; where
one label is a substring of another (चावल vs बासी चावल) the longer one is matched first.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# A believable ordinary kitchen (vegetarian household, small town). Label texts are exactly what
# Gradio renders (emoji + label from kitchen.py); parentheticals disambiguate substrings
# ("चावल (कच्चे)" vs "बासी / पके हुए चावल" vs "चावल का पोहा").
TICKS = [
    ("आटा · चावल", ["🌾 आटा", "🍚 चावल (कच्चे)", "🥣 अरहर (तूअर) दाल", "🍜 मैगी / नूडल्स"]),
    ("सब्ज़ी", ["🥔 आलू", "🧅 प्याज़", "🍅 टमाटर", "🥦 फूलगोभी"]),
    ("डेयरी", ["🥣 दही"]),
    ("मसाले", ["🧂 नमक", "🫗 तेल", "🟡 हल्दी", "🌶️ लाल मिर्च पाउडर", "🟤 धनिया पाउडर"]),
]
EXTRAS = "thoda basi chawal bhi hai, aadha gobhi bhi"


def tick_group(page, group_label, items):
    grp = page.locator("fieldset, .group").filter(has_text=group_label).first
    for item in items:
        lab = grp.locator("label").filter(has_text=item).first
        lab.click()
        page.wait_for_timeout(250)


def shoot(url: str, outdir: str):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 412, "height": 915}, device_scale_factor=2)
        page.goto(url, wait_until="domcontentloaded", timeout=180000)
        page.wait_for_selector("input[type=checkbox]", timeout=60000)
        page.wait_for_timeout(4000)

        # 1 — the kitchen inventory, mid-ticking (this IS the product)
        for group, items in TICKS:
            tick_group(page, group, items)
        page.wait_for_timeout(500)
        page.screenshot(path=str(out / "1-kitchen.png"))

        # 2 — the lazy part: free text + "kam mehnat" already selected
        page.get_by_label("और क्या है?", exact=False).first.fill(EXTRAS)
        page.wait_for_timeout(400)
        page.get_by_role("button", name="बताओ").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.screenshot(path=str(out / "2-lazy.png"))

        # 3 — Gemma writing the mood (status line)
        page.get_by_role("button", name="बताओ").click()
        page.wait_for_timeout(4000)
        page.screenshot(path=str(out / "3-thinking.png"))

        # 4 — tonight's cards (waits for the real Gemma call to land)
        page.wait_for_function(
            "() => { const c = document.querySelector('#cards'); return !!(c && (c.innerText.includes('बनाने का तरीका') || c.innerText.includes('बन सकता है'))); }",
            timeout=300000,
        )
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / "4-dinner.png"), full_page=True)

        # 5 — the one-away alternatives + shopping list
        page.locator("#shopping").scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        page.screenshot(path=str(out / "5-shopping.png"))
        browser.close()
    print("done:", sorted(p.name for p in out.glob("*.png")))


if __name__ == "__main__":
    t0 = time.time()
    shoot(sys.argv[1], sys.argv[2])
    print(f"took {time.time() - t0:.0f}s")
