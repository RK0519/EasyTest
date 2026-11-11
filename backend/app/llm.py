"""LLM steps using Groq: (1) classify the site and find flows, (2) write test cases per flow."""
import asyncio, json, os, re
from groq import AsyncGroq, RateLimitError, BadRequestError

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
client = AsyncGroq()  # reads GROQ_API_KEY

PLAN_SYSTEM = """You are a senior QA architect. Given crawl data from a website, identify the
type of site and the end-to-end user flows that matter, in the order a real user would meet them
(start with account access such as signup/login if the site has it, finish with the final goal
such as checkout, order, trade, application or enquiry submission).
Mark a flow observed=true only if its key pages/forms appear in the crawl data; otherwise
observed=false (inferred from how this type of site normally works).
Reply with JSON only:
{"site_type": str, "summary": str (one sentence),
 "flows": [{"name": str, "description": str, "observed": bool, "page_urls": [str]}]}
Give 5 to 7 flows."""

CASES_SYSTEM = """You are a senior QA engineer writing functional test cases for ONE user flow.
Use the real field names, button labels and validation hints from the crawl data when present.
Cover positive, negative, boundary and edge cases (empty fields, invalid formats, wrong
credentials/OTP, max length, double submit, session expiry, etc.) as relevant.
Never invent real credentials; use clearly fake test data.
Reply with JSON only:
{"test_cases": [{"title": str, "preconditions": str, "steps": [str], "test_data": str,
 "expected_result": str, "priority": "High"|"Medium"|"Low",
 "type": "Positive"|"Negative"|"Boundary"|"Edge"}]}
Write 6 to 8 test cases."""


def _parse(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e + 1])


async def _ask(system: str, user: str, max_tokens: int):
    json_mode = True
    for attempt in range(5):
        kwargs = dict(
            model=MODEL, max_tokens=max_tokens, temperature=0.3,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            r = await client.chat.completions.create(**kwargs)
            return _parse(r.choices[0].message.content or "")
        except RateLimitError:
            await asyncio.sleep(15 * (attempt + 1))  # free tier: wait and retry
        except (BadRequestError, json.JSONDecodeError, ValueError):
            json_mode = False  # retry without strict JSON mode; our parser handles it
    raise RuntimeError("Could not get valid JSON from the model after 5 tries")


def _compact(pages: list, limit: int) -> str:
    return json.dumps(pages, ensure_ascii=False, separators=(",", ":"))[:limit]


async def plan_flows(crawl: dict) -> dict:
    user = f"Website: {crawl['url']}\nCrawl errors: {crawl['errors']}\nPages:\n{_compact(crawl['pages'], 7000)}"
    return await _ask(PLAN_SYSTEM, user, 4000)


async def cases_for_flow(site_type: str, flow: dict, crawl: dict) -> list:
    urls = set(flow.get("page_urls") or [])
    related = [p for p in crawl["pages"] if p["url"] in urls] or crawl["pages"][:2]
    user = (f"Site type: {site_type}\nWebsite: {crawl['url']}\n"
            f"Flow: {flow['name']} - {flow['description']}\n"
            f"Observed on the live site: {flow['observed']}\n"
            f"Relevant page data:\n{_compact(related, 3500)}")
    data = await _ask(CASES_SYSTEM, user, 8000)
    return data.get("test_cases", [])