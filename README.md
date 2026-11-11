# EasyTest - Test Case Agent

Give it a website URL; it crawls the site, identifies the site type and user flows,
and generates functional test cases per flow (exportable to Excel).

## Run the backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env                                   # then add your ANTHROPIC_API_KEY
uvicorn app.main:app --port 8000                       # no --reload on Windows (Playwright needs it)
```

## Run the frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

## How it works
1. `crawler.py` opens the site with Playwright, scores links by journey keywords
   (login, cart, checkout, admission, fees...) and records forms, inputs and buttons.
2. `llm.py` asks Claude to classify the site and list its flows (observed vs inferred).
3. One call per flow (run in parallel) writes the test cases as JSON.
4. `export.py` turns them into an Excel sheet.

Flows behind login/OTP/CAPTCHA are tagged **Inferred** because the crawler can't see them.
