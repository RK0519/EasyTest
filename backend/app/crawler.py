"""Playwright crawler: loads the site, finds the pages that matter, and builds
a compact 'interaction map' (forms, inputs, buttons, nav) for each page."""
import asyncio
import os
from urllib.parse import urlparse, urldefrag
from playwright.async_api import async_playwright

# Words that hint at an important user-journey page, with a weight each.
KEYWORDS = {
    "login": 10, "log in": 10, "sign in": 10, "signin": 10, "sign up": 9,
    "signup": 9, "register": 9, "create account": 9, "account": 5,
    "cart": 8, "basket": 8, "bag": 6, "checkout": 9, "pay": 7, "payment": 8,
    "order": 6, "search": 6, "menu": 5, "product": 5, "shop": 5,
    "admission": 8, "apply": 7, "course": 6, "program": 5, "fee": 6,
    "contact": 6, "enquiry": 6, "inquiry": 6, "student": 6, "portal": 6,
    "dashboard": 6, "profile": 5, "wishlist": 4, "track": 5, "fund": 6,
    "trade": 6, "invest": 6, "portfolio": 6, "book": 6, "booking": 7,
    "pricing": 5, "plans": 5, "forgot": 5, "support": 4, "help": 3,
}

EXTRACT_JS = """() => {
  const txt = e => (e.innerText || e.value || e.getAttribute('aria-label') || e.placeholder || '').trim().replace(/\\s+/g,' ').slice(0,80);
  const inputs = [...document.querySelectorAll('input,select,textarea')]
    .filter(e => e.type !== 'hidden').slice(0,40).map(e => ({
      tag: e.tagName.toLowerCase(), type: e.type || '', name: e.name || e.id || '',
      placeholder: e.placeholder || '',
      label: ((e.labels && e.labels[0]) ? e.labels[0].innerText : (e.getAttribute('aria-label') || '')).trim().slice(0,60),
      required: !!e.required, pattern: e.pattern || '',
      maxlength: e.maxLength > 0 ? e.maxLength : null }));
  const forms = [...document.forms].slice(0,10).map(f => ({
    action: f.getAttribute('action') || '', method: f.method,
    fields: f.querySelectorAll('input:not([type=hidden]),select,textarea').length }));
  const buttons = [...document.querySelectorAll('button,[role=button],input[type=submit]')]
    .map(txt).filter(Boolean).slice(0,30);
  const links = [...document.querySelectorAll('a[href]')]
    .map(a => ({text: txt(a), href: a.href})).filter(l => l.text).slice(0,400);
  const headings = [...document.querySelectorAll('h1,h2,h3')].map(txt).filter(Boolean).slice(0,15);
  const meta = document.querySelector('meta[name=description]');
  const captcha = !!document.querySelector('iframe[src*=captcha],iframe[src*=recaptcha],[class*=captcha],[id*=captcha]');
  return {title: document.title, description: meta ? meta.content : '',
          headings, inputs, forms, buttons, links, captcha};
}"""

# --- Settings that make the browser look less like a bot ---
LAUNCH_ARGS = ["--disable-http2", "--disable-blink-features=AutomationControlled",
               "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
STEALTH = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _norm(url: str) -> str:
    return urldefrag(url)[0].rstrip("/")


def _score(link: dict, base_host: str) -> int:
    host = urlparse(link["href"]).netloc.replace("www.", "")
    if host != base_host or not link["href"].startswith("http"):
        return 0
    blob = (link["text"] + " " + urlparse(link["href"]).path).lower()
    return sum(w for k, w in KEYWORDS.items() if k in blob)


async def _snapshot(page, url: str) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass  # SPAs with long polling never go idle; carry on
    data = await page.evaluate(EXTRACT_JS)
    data["url"] = page.url
    return data


async def _open(p, headless: bool):
    browser = await p.chromium.launch(headless=headless, args=LAUNCH_ARGS)
    ctx = await browser.new_context(
        user_agent=USER_AGENT, viewport={"width": 1366, "height": 850},
        locale="en-IN", timezone_id="Asia/Kolkata")
    await ctx.add_init_script(STEALTH)
    return browser, await ctx.new_page()


async def crawl(url: str, max_pages: int = 6, on_progress=None) -> dict:
    if not url.startswith("http"):
        url = "https://" + url
    base_host = urlparse(url).netloc.replace("www.", "")
    pages, errors = [], []

    async with async_playwright() as p:
        home, last_err, browser, page = None, None, None, None
        modes = (True,) if os.getenv("RENDER") else (True, False)  # no screen on Render
        for headless in modes:  # on your laptop, the second try opens a visible window
            if on_progress and not headless:
                on_progress("Blocked in headless mode, retrying with a visible browser")
            browser, page = await _open(p, headless)
            try:
                home = await _snapshot(page, url)
                break
            except Exception as e:
                last_err = e
                await browser.close()

        if home is None:
            return {"url": url, "pages": [],
                    "errors": [f"Homepage failed to load (site likely blocks bots): {last_err}"]}

        seen = {_norm(url), _norm(home["url"])}
        pages.append(home)

        ranked = sorted(home["links"], key=lambda l: _score(l, base_host), reverse=True)
        queue = []
        for l in ranked:
            if _score(l, base_host) <= 0:
                break
            n = _norm(l["href"])
            if n not in seen:
                seen.add(n)
                queue.append(l["href"])
            if len(queue) >= max_pages - 1:
                break

        for i, link in enumerate(queue, 1):
            if on_progress:
                on_progress(f"Visiting page {i + 1} of {len(queue) + 1}")
            try:
                pages.append(await _snapshot(page, link))
            except Exception as e:
                errors.append(f"{link}: {str(e)[:120]}")
        await browser.close()

    # Trim: keep nav link labels only, to keep the LLM prompt small.
    for pg in pages:
        pg["nav"] = list(dict.fromkeys(l["text"] for l in pg.pop("links")))[:40]
    return {"url": url, "pages": pages, "errors": errors}