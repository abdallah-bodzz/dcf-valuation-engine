# DCF Valuation Engine

A full DCF valuation tool built in Python. Enter a ticker, set your assumptions, get an intrinsic value estimate — backed by real financials from Yahoo Finance and a sensitivity table that shows the range of outcomes.

The UI (dark-themed dashboard with charts, heatmap, and financial tables) was designed and built entirely by Claude.

---

## What it does

- Pulls real annual financials via yfinance (income statement, cash flow, balance sheet)
- Projects revenue forward using a user-supplied CAGR
- Projects costs using trailing 3-year average margins — same method sell-side analysts use
- Builds a fully reconciled income statement for each forecast year (`Revenue → COGS → Gross Profit → OpEx → EBIT`)
- Calculates unlevered FCF, discounts at WACC, adds terminal value via Gordon Growth Model
- Bridges EV → Equity Value → intrinsic price per share
- Runs a 7×7 sensitivity matrix across WACC and terminal growth rate, with a heatmap anchored to current market price (not to the matrix min/max — a common mistake)

---

## Stack

```
Python · FastAPI · yfinance · Chart.js · single-file HTML frontend
```

---

## Quick start

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# open http://localhost:8000
```

Works best with US-listed large-caps (AAPL, MSFT, GOOGL, JPM, etc.). Some international tickers have incomplete financial statement rows — the app surfaces a warning when that happens.

---

## Project structure

```
main.py        ← FastAPI app and route handlers
data.py        ← yfinance fetching, cleaning, normalization
forecast.py    ← revenue and cost projection
valuation.py   ← DCF math, terminal value, sensitivity matrix
models.py      ← Pydantic schemas for request/response validation
index.html     ← full frontend (HTML + CSS + JS + Chart.js, no build step)
```

Each file has one job. You can swap yfinance for another data source, or replace the frontend, without touching the financial math.

---

## A few implementation notes

**Why OpEx is derived, not independently projected**

Projecting COGS margin and EBIT margin separately creates an implicit OpEx that doesn't reconcile with Gross Profit. Instead, `OpEx = Gross Profit − EBIT` historically, then that margin is projected. This ensures the income statement is always an identity, not an approximation.

**Why CapEx sign is checked before negating**

yfinance stores CapEx as negative (cash outflow convention), so the model negates it. But some tickers already report it positive. The code checks the median sign before deciding whether to negate, which prevents double-negation errors.

**Why the sensitivity heatmap is anchored to market price**

If you color a heatmap relative to its own min/max, the "greenest" cell looks attractive even if every cell in the matrix implies the stock is overvalued. Anchoring to current market price gives each cell an honest signal.

**Why WACC is a user input**

Computing WACC from scratch requires a beta estimate, a market risk premium assumption, and a current cost of debt — all of which are themselves debatable. Letting the user supply WACC and explore outcomes across the sensitivity table is more transparent than hiding three additional assumptions inside a derived number.

---

## Known limitations

- Flat CAGR, no growth fade — overvalues high-growth companies at the terminal year. Use a conservative rate and check the sensitivity table.
- Margins are backward-looking. If the business model is changing, historical averages are a weak anchor.
- yfinance data quality varies. Smaller or international tickers often have missing or mislabeled rows.
- No segment-level modeling, no minority interest adjustment, no preferred shares.

---

## API

```
POST /api/valuation   full DCF pipeline, returns summary + forecast + sensitivity
GET  /api/health      sanity check
GET  /                serves the frontend
```

Request body:
```json
{
  "ticker": "AAPL",
  "forecast_years": 5,
  "revenue_growth_rate": 0.08,
  "wacc": 0.10,
  "terminal_growth_rate": 0.025,
  "tax_rate": 0.21
}
```

`terminal_growth_rate` must be strictly less than `wacc` — validated by Pydantic before anything runs.

---

*For educational and research purposes. Not investment advice.*