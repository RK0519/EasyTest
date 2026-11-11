import asyncio, os, uuid
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import crawler, llm
from .export import to_excel

app = FastAPI(title="EasyTest")
app.add_middleware(CORSMiddleware,
                   allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
                   allow_methods=["*"], allow_headers=["*"])

JOBS: dict[str, dict] = {}  # in-memory; swap for Redis/DB if you deploy this


class JobRequest(BaseModel):
    url: str
    max_pages: int = Field(6, ge=1, le=15)


def _set(job, **kw):
    job.update(kw)


async def run_job(job_id: str, req: JobRequest):
    job = JOBS[job_id]
    try:
        _set(job, stage="crawling", message="Opening the site and mapping its pages")
        crawl = await crawler.crawl(
            req.url, req.max_pages,
            on_progress=lambda m: _set(job, message=m))
        job["pages_crawled"] = len(crawl["pages"])
        job["warnings"] = crawl["errors"]
        if any(p.get("captcha") for p in crawl["pages"]):
            job["warnings"].append("CAPTCHA detected; some flows are inferred, not observed.")

        _set(job, stage="planning", message="Identifying the site type and user flows")
        plan = await llm.plan_flows(crawl)
        flows = plan["flows"]
        job.update(site_type=plan["site_type"], summary=plan["summary"], flows=flows)

        _set(job, stage="generating", message=f"Writing test cases for {len(flows)} flows")
        results = []
        for i, f in enumerate(flows, 1):
            _set(job, message=f"Writing test cases: {f['name']} ({i} of {len(flows)})")
            try:
                results.append(await llm.cases_for_flow(plan["site_type"], f, crawl))
            except Exception as e:
                results.append(e)

        cases, n = [], 1
        for flow, res in zip(flows, results):
            if isinstance(res, Exception):
                job["warnings"].append(f"'{flow['name']}' failed: {str(res)[:100]}")
                continue
            for tc in res:
                cases.append({
                    "id": f"TC-{n:03d}", "flow": flow["name"],
                    "source": "Observed" if flow["observed"] else "Inferred",
                    "title": tc.get("title", ""), "type": tc.get("type", "Positive"),
                    "priority": tc.get("priority", "Medium"),
                    "preconditions": tc.get("preconditions", ""),
                    "steps": tc.get("steps", []), "test_data": tc.get("test_data", ""),
                    "expected_result": tc.get("expected_result", "")})
                n += 1
        _set(job, test_cases=cases, stage="done", status="done",
             message=f"Generated {len(cases)} test cases")
    except Exception as e:
        _set(job, status="error", stage="error", message=f"{type(e).__name__}: {e}")


@app.post("/api/jobs")
async def create_job(req: JobRequest):
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {"id": job_id, "url": req.url, "status": "running", "stage": "queued",
                    "message": "Starting", "warnings": [], "flows": [], "test_cases": []}
    asyncio.create_task(run_job(job_id, req))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job")
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}/export")
async def export(job_id: str):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Results not ready")
    return Response(
        to_excel(job["test_cases"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="test-cases-{job_id}.xlsx"'})