# DCF Valuation & Forecast Engine

A production-grade **Discounted Cash Flow (DCF)** valuation system built in Python. Enter any publicly traded stock ticker, set your assumptions, and get a full intrinsic value estimate — backed by real financial data, a mathematically consistent income statement, and a sensitivity analysis that shows you the range of outcomes.

Built to demonstrate real financial modeling skills, not just a dashboard wrapper.

```
Stack: Python · FastAPI · yfinance · Chart.js · Single-file HTML frontend
Data:  Real annual financials via yfinance (income statement, cash flow, balance sheet)
```

---

## Table of Contents

- [What It Does](#what-it-does)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Application Flow](#application-flow)
- [Financial Model — Full Walkthrough](#financial-model--full-walkthrough)
  - [Step 1 · Data Sourcing & Cleaning](#step-1--data-sourcing--cleaning)
  - [Step 2 · Revenue Forecasting](#step-2--revenue-forecasting)
  - [Step 3 · Cost Projection — The Common-Size Method](#step-3--cost-projection--the-common-size-method)
  - [Step 4 · Income Statement Reconciliation](#step-4--income-statement-reconciliation)
  - [Step 5 · Free Cash Flow Calculation](#step-5--free-cash-flow-calculation)
  - [Step 6 · Discounted Cash Flow (DCF)](#step-6--discounted-cash-flow-dcf)
  - [Step 7 · Terminal Value](#step-7--terminal-value)
  - [Step 8 · EV → Equity Value → Price Bridge](#step-8--ev--equity-value--price-bridge)
  - [Step 9 · Sensitivity Analysis](#step-9--sensitivity-analysis)
- [UI Components](#ui-components)
- [API Reference](#api-reference)
- [Design Decisions & Tradeoffs](#design-decisions--tradeoffs)
- [Known Limitations](#known-limitations)
- [Glossary](#glossary)

---

## What It Does

Given a ticker symbol and a handful of assumptions, the engine:

1. **Pulls real annual financials** from Yahoo Finance — income statement, cash flow statement, and balance sheet
2. **Projects revenue forward** using a user-supplied CAGR
3. **Projects costs** using trailing 3-year average margins anchored to historical data — the same method used by sell-side equity analysts
4. **Builds a fully reconciled income statement** for each forecast year (`Revenue → COGS → Gross Profit → OpEx → EBIT`)
5. **Calculates Free Cash Flow** for each forecast year using the standard unlevered FCF formula
6. **Discounts all FCFs** to present value using WACC
7. **Calculates Terminal Value** using the Gordon Growth Model (perpetuity with growth)
8. **Bridges Enterprise Value → Equity Value → Intrinsic Price per share**
9. **Runs a 7×7 sensitivity matrix** across WACC and terminal growth rate, with heatmap coloring anchored to the current market price

The output tells you what a stock is *worth* under your assumptions — and how sensitive that estimate is to the assumptions themselves.

---

## Quick Start

**Requirements:** Python 3.11+

```bash
# 1. Clone the repo
git clone https://github.com/yourname/valuation-engine.git
cd valuation-engine

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
uvicorn main:app --reload --port 8000

# 4. Open in your browser
open http://localhost:8000
```

**requirements.txt**
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
yfinance==0.2.44
pandas==2.2.2
numpy==1.26.4
pydantic==2.7.4
```

> **Note:** yfinance pulls data from Yahoo Finance's public API. Data availability varies by ticker. US-listed large-caps (AAPL, MSFT, AMZN, GOOGL, JPM, etc.) work best. Some international tickers or small-caps may have incomplete financial statements — the engine surfaces data quality warnings when this happens.

---

## Project Structure

```
valuation_engine/
│
├── main.py          ← FastAPI app — all routes, request orchestration
├── models.py        ← Pydantic schemas — request validation & response types
├── data.py          ← yfinance data layer — fetching, cleaning, normalization
├── forecast.py      ← Revenue & cost projection engine
├── valuation.py     ← DCF math — terminal value, EV bridge, sensitivity matrix
├── requirements.txt
│
└── frontend/
    └── index.html   ← Single-file dark-theme dashboard (HTML + CSS + JS + Chart.js)
```

**Why this structure?** Each file has exactly one responsibility. The separation means you can swap out any layer independently — replace yfinance with a Bloomberg API, add a database cache, or change the frontend framework — without touching the financial math.

| File | Responsibility | Depends On |
|---|---|---|
| `data.py` | Fetch & normalize raw financial data | `yfinance` |
| `forecast.py` | Project income statement & FCFs forward | `data.py` |
| `valuation.py` | DCF, terminal value, sensitivity matrix | `forecast.py`, `data.py` |
| `main.py` | HTTP API, orchestrate the pipeline | All of the above |
| `models.py` | Input validation, response schemas | `pydantic` |

---

## Application Flow

The request lifecycle from the moment you click **Run Model**:

```
Browser
  │
  │  POST /api/valuation
  │  { ticker, wacc, growth_rate, tgr, tax_rate, forecast_years }
  ▼
FastAPI (main.py)
  │
  ├─► data.py · CompanyData(ticker)
  │     ├─ yf.Ticker(ticker).financials      → income statement (annual)
  │     ├─ yf.Ticker(ticker).cashflow        → cash flow statement (annual)
  │     ├─ yf.Ticker(ticker).balance_sheet   → balance sheet (annual)
  │     └─ yf.Ticker(ticker).info            → current price, shares outstanding
  │
  ├─► forecast.py · build_forecast(company, ...)
  │     ├─ Compute trailing 3-year margins (COGS, OpEx, D&A, CapEx, WC / Revenue)
  │     ├─ Project revenue: R(t) = R(0) × (1 + g)^t
  │     ├─ Project income statement (fully reconciled)
  │     ├─ Calculate FCF per year
  │     └─ Discount each FCF to PV using WACC
  │
  ├─► valuation.py · calculate_dcf(forecast, company, ...)
  │     ├─ Sum PV of all forecast FCFs
  │     ├─ Gordon Growth Model → Terminal Value
  │     ├─ EV = PV(FCF) + PV(Terminal Value)
  │     ├─ Equity Value = EV − Net Debt
  │     └─ Intrinsic Price = Equity Value / Diluted Shares
  │
  ├─► valuation.py · build_sensitivity_matrix(forecast, company, ...)
  │     └─ 7 × 7 grid: re-run DCF for every (WACC, TGR) combination
  │
  └─► Assemble ValuationResponse → JSON → Browser
        │
        ├─ Summary cards (ticker, market price, intrinsic price, EV, equity value)
        ├─ FCF chart (historical bars + projected bars + discounted FCF line)
        ├─ EV bridge (step-by-step from PV(FCF) to intrinsic price)
        ├─ Income statement table (projected, reconciled)
        ├─ Cash flow table (NOPAT → FCF → PV bridge)
        ├─ Historical table (actual yfinance data)
        ├─ Sensitivity heatmap (7 × 7, colored vs. market price)
        └─ Margin bars + assumptions panel
```

---

## Financial Model — Full Walkthrough

This section explains exactly what the engine does mathematically, and *why* each choice was made the way it was. Written for both non-finance developers and finance readers who want to validate the methodology.

---

### Step 1 · Data Sourcing & Cleaning

**Source:** Yahoo Finance public API via the `yfinance` Python library.

**Statements fetched (annual frequency):**
- Income statement → `yf.Ticker().financials`
- Cash flow statement → `yf.Ticker().cashflow`
- Balance sheet → `yf.Ticker().balance_sheet`
- Company info → `yf.Ticker().info` (current price, shares outstanding)

**Key normalization applied in `data.py`:**

| Problem | Fix |
|---|---|
| yfinance returns columns newest-first | Reversed to chronological order |
| Values are in raw USD (not thousands) | Divided by 1e9 → converted to **billions** |
| CapEx is stored as a negative number (cash outflow convention) | Checked median sign; negated only if actually negative (prevents double-negation for tickers that store it positive) |
| Row names differ between tickers (e.g. "Cost Of Revenue" vs "Reconciled Cost Of Revenue") | Alias list — tries multiple row names in order, uses first found |
| Missing rows for some tickers | Returns NaN series; surfaces a user-visible warning; margin calculations treat NaN as 0 |
| Working Capital not directly available | Computed: `WC = Current Assets − Current Liabilities` |
| Net Debt not directly available | Computed: `Net Debt = Total Debt − Cash & Equivalents` |

**Data extracted:**

```python
Revenue          = income["Total Revenue"]
COGS             = income["Cost Of Revenue"]          # or aliases
Gross Profit     = income["Gross Profit"]
EBIT             = income["EBIT"]                     # or "Operating Income"
D&A              = cashflow["Depreciation And Amortization"]
CapEx            = cashflow["Capital Expenditure"]    # sign-corrected
Working Capital  = balance["Current Assets"] - balance["Current Liabilities"]
Net Debt         = balance["Total Debt"] - balance["Cash And Cash Equivalents"]
Shares           = info["sharesOutstanding"]          # diluted, most current
Current Price    = info["currentPrice"]
```

---

### Step 2 · Revenue Forecasting

**Method: Constant CAGR (user-supplied)**

```
Revenue(t) = Revenue(0) × (1 + g)^t
```

Where:
- `Revenue(0)` = the most recent annual revenue from the income statement
- `g` = annual growth rate supplied by the user (e.g. `0.08` for 8%)
- `t` = year number in the forecast (1, 2, 3, ...)

**Why a flat CAGR?**

A flat CAGR is transparent, auditable, and easy to stress-test. More complex approaches (ARIMA, segment-level modeling, analyst consensus) add parameters without improving explainability. In an interview or peer review context, you can defend a CAGR assumption clearly. You cannot easily defend why your ARIMA(2,1,1) produced a specific number.

**What to think about when setting this input:**

- Historical revenue CAGR (shown in the Historical tab) is a natural anchor
- Management guidance, if available, is a better forward-looking anchor
- Industry growth rates provide context
- Higher growth rates increase intrinsic value — be conservative and then use the sensitivity table to understand the upside case

---

### Step 3 · Cost Projection — The Common-Size Method

**Core idea:** express every cost line as a percentage of revenue, compute the trailing 3-year average of that ratio, and apply it to projected revenue.

This is called **common-size analysis** and is standard practice in equity research.

```
Margin(X) = average( X(t) / Revenue(t) ) for t in [last 3 years]
```

Margins computed:

| Margin | Formula | Use |
|---|---|---|
| COGS Margin | `avg(COGS / Revenue)` | Project COGS |
| OpEx Margin | `avg((Gross Profit − EBIT) / Revenue)` | Project operating expenses |
| D&A Margin | `avg(D&A / Revenue)` | Cash flow add-back |
| CapEx Margin | `avg(CapEx / Revenue)` | Cash flow deduction |
| WC Margin | `avg(Working Capital / Revenue)` | Working capital requirement |

**Why 3-year trailing average?**

A single year's margin can be distorted by one-off events (a write-down, a pandemic year, a one-time restructuring charge). Three years provides a smoothed view of the business's normalized cost structure while still being recent. Analysts typically use 3–5 years.

**Why OpEx is derived, not independently projected:**

A subtle but important correctness issue. If you project COGS and EBIT margins independently from history, their sum implies an OpEx that doesn't reconcile with Gross Profit. The fix:

```
OpEx = Gross Profit − EBIT   (historical, by definition)
OpEx Margin = avg(OpEx / Revenue)
```

This ensures the projected income statement is always internally consistent.

---

### Step 4 · Income Statement Reconciliation

The projected income statement must satisfy these identities in every forecast year:

```
Revenue
  − COGS                           (= Revenue × cogs_margin)
  ─────────────────────────────────
  = Gross Profit                   (identity: Revenue − COGS)
  − OpEx                           (= Revenue × opex_margin)
  ─────────────────────────────────
  = EBIT                           (identity: Gross Profit − OpEx)
  × (1 − tax_rate)
  ─────────────────────────────────
  = NOPAT
```

**These are identities, not approximations.** The code enforces them structurally:

```python
cogs         = revenue * cogs_margin
gross_profit = revenue - cogs          # always exact
opex         = revenue * opex_margin
ebit         = gross_profit - opex     # always exact
nopat        = ebit * (1 - tax_rate)
```

`ebit_margin` (stored for display purposes) is a *derived* quantity, not an input to the model. It will match `1 − cogs_margin − opex_margin` by construction.

---

### Step 5 · Free Cash Flow Calculation

**Formula:**

```
FCF = NOPAT + D&A − CapEx − ΔWorking Capital
```

**Line by line:**

| Term | Sign | Explanation |
|---|---|---|
| `NOPAT` | + | Net Operating Profit After Tax — cash earnings as if the business were 100% equity-financed (no interest expense) |
| `D&A` | + | Depreciation & Amortization reduced EBIT (and therefore NOPAT), but no cash actually left the business. We add it back. |
| `CapEx` | − | Actual cash spent on maintaining and growing the asset base. Must be subtracted because it is a real outflow not reflected in EBIT. |
| `ΔWorking Capital` | − | An *increase* in working capital means the business is tying up more cash in inventory, receivables, etc. This is a cash outflow. A *decrease* is a cash inflow. |

**Why NOPAT instead of Net Income?**

DCF values the business *independent of its capital structure*. Interest expense is a payment to debt holders — it should not reduce the cash flows available to *all* capital providers (debt + equity). NOPAT = EBIT × (1 − tax_rate) deliberately excludes interest, making the FCF "unlevered." The effect of debt is captured separately in the EV → Equity Value bridge via Net Debt.

**Working Capital sign convention (a common source of errors):**

```
ΔWC(t) = WC(t) − WC(t−1)

ΔWC > 0  →  WC grew  →  cash OUTFLOW  →  subtract from FCF
ΔWC < 0  →  WC shrank →  cash INFLOW   →  adds to FCF (double negative)
```

For the first historical year (no prior period to diff against), ΔWC is set to 0.

**Discounting:**

Each FCF is discounted to present value at time `t = 0`:

```
PV(FCF_t) = FCF_t / (1 + WACC)^t
```

The `(1 + WACC)^t` term is the discount factor. It represents the opportunity cost: a dollar received `t` years in the future is worth less than a dollar today because of the time value of money and the riskiness of the cash flows.

---

### Step 6 · Discounted Cash Flow (DCF)

The sum of all discounted FCFs over the explicit forecast period:

```
PV(FCFs) = Σ [ FCF(t) / (1 + WACC)^t ]   for t = 1 to n
```

**WACC — Weighted Average Cost of Capital:**

WACC is the blended required return of all capital providers (equity + debt):

```
WACC = (E/V) × Re + (D/V) × Rd × (1 − tax_rate)

Where:
  E   = Market value of equity
  D   = Market value of debt
  V   = E + D (total capital)
  Re  = Cost of equity (e.g. via CAPM: Rf + β × ERP)
  Rd  = Pre-tax cost of debt (yield on outstanding bonds)
```

**This model accepts WACC as a user input** rather than computing it from scratch. Computing WACC from first principles requires a reliable beta estimate, a market risk premium assumption, and a current cost of debt — all of which can themselves be debated. For a standalone model, it is more transparent to let the user supply their WACC assumption and then explore the range of outcomes via the sensitivity table. Typical WACC values: 7–12% for large-cap developed-market companies.

---

### Step 7 · Terminal Value

The **Terminal Value (TV)** captures the value of all cash flows beyond the explicit forecast period. It is computed using the **Gordon Growth Model** (also called the perpetuity growth model):

```
TV = FCF(n) × (1 + g_terminal) / (WACC − g_terminal)
```

Where:
- `FCF(n)` = Free Cash Flow in the final forecast year
- `g_terminal` = the perpetuity growth rate — the assumed long-run growth rate *forever* after year n
- `WACC` = discount rate (same as above)

This is discounted back to present value:

```
PV(TV) = TV / (1 + WACC)^n
```

**Critical constraint: WACC > g_terminal (strictly)**

If `g_terminal ≥ WACC`, the denominator `(WACC − g_terminal)` becomes zero or negative, and the formula produces an infinite or negative terminal value. This is nonsensical. The model validates this constraint in Pydantic before any computation runs.

**What does g_terminal mean in practice?**

It represents the rate at which the business's free cash flows grow *in perpetuity*. A reasonable upper bound is the long-run nominal GDP growth rate of the economy (~2.5–3.5% for developed markets). No business can grow faster than the economy forever — if it did, it would eventually become larger than the entire economy. Conservative analysts use 2–2.5%. Aggressive assumptions above 3.5% should be viewed with skepticism.

**Terminal Value as a percentage of Enterprise Value:**

This metric is surfaced prominently in the UI because it is one of the most important disclosures in any DCF model:

- A **5-year forecast** typically results in TV representing **70–85%** of EV
- A **10-year forecast** typically results in TV representing **50–65%** of EV

This is not a flaw — it reflects the mathematical reality that most of a company's value lies in the long run. But it does mean that the terminal value assumptions (WACC, g_terminal) drive most of the output. This is exactly why the sensitivity table exists.

---

### Step 8 · EV → Equity Value → Price Bridge

```
Enterprise Value  =  PV(FCFs)  +  PV(Terminal Value)
                  ↓
Equity Value      =  Enterprise Value  −  Net Debt
                  ↓
Intrinsic Price   =  Equity Value  /  Diluted Shares Outstanding
```

**Why subtract Net Debt?**

Enterprise Value (EV) is the total value of the *business* — the value available to *all* capital providers (debt holders and equity holders). Debt holders have a prior claim: they get paid first. So to find what's left for equity holders (shareholders), we subtract Net Debt.

```
Net Debt = Total Financial Debt − Cash & Cash Equivalents
```

- If Net Debt is **positive** (company has more debt than cash): equity value is less than EV
- If Net Debt is **negative** (company has more cash than debt, i.e. "net cash"): equity value exceeds EV — cash accrues to shareholders

**Shares Outstanding:**

We use **diluted** shares outstanding — this includes the dilutive effect of stock options, warrants, and convertible instruments. Using basic shares would overstate the intrinsic price per share by ignoring these obligations.

---

### Step 9 · Sensitivity Analysis

The sensitivity table runs the full DCF for every combination of WACC and terminal growth rate in a 7×7 grid:

```
WACC values:  [7%, 8%, 9%, 10%, 11%, 12%, 13%]
TGR values:   [1.0%, 1.5%, 2.0%, 2.5%, 3.0%, 3.5%, 4.0%]
```

For each `(WACC, TGR)` pair:
1. Re-discount the same FCF stream with the new WACC
2. Recompute terminal value with the new WACC and TGR
3. Re-run the EV → equity value → price bridge

This produces 49 intrinsic price estimates from a single FCF forecast.

**Heatmap coloring (anchored to market price, not to matrix min/max):**

| Color | Meaning |
|---|---|
| 🟢 Dark green | Intrinsic price > +30% above market → significantly undervalued |
| 🟢 Light green | Intrinsic price +10% to +30% above market → moderately undervalued |
| ⬜ Neutral | Intrinsic price within ±10% of market → approximately fairly valued |
| 🔴 Light red | Intrinsic price −10% to −30% below market → moderately overvalued |
| 🔴 Dark red | Intrinsic price < −30% below market → significantly overvalued |

Anchoring to market price is a deliberate design choice. Coloring relative to the matrix's own min/max (a common mistake) would make the cell with the highest intrinsic price look green even if every cell in the matrix says the stock is overvalued. Anchoring to market price gives the heatmap honest signal.

The **base case cell** (your input WACC and TGR) is outlined in blue.

---

## UI Components

The frontend is a single `index.html` file with no build step, no npm, no framework — just HTML, CSS, and vanilla JavaScript with Chart.js loaded from a CDN.

### Header
Fixed sticky bar. Shows the engine name, live "online" indicator (green pulsing dot), and keyboard shortcut hint (`Enter ↵ to run`).

### Model Parameters Panel
Six inputs + a run button:

| Input | What it is | Typical range |
|---|---|---|
| **Ticker** | Any exchange-listed symbol. Normalized to uppercase. | `AAPL`, `MSFT`, `0005.HK` |
| **Revenue Growth %** | Your forward CAGR assumption | 3–25% depending on company |
| **WACC %** | Discount rate | 7–13% for large caps |
| **Terminal Growth %** | Perpetuity growth rate (must be < WACC) | 1.5–3.5% |
| **Tax Rate %** | Effective corporate tax rate | 15–28% |
| **Forecast Years** | Explicit forecast horizon | 3–10 years |

While the model is running, all inputs are disabled, the button shows the ticker name and a loading indicator, and a status bar appears with a spinner.

### Summary Cards
Five cards across the top of the results:
- **Company** — ticker + full company name
- **Market Price** — current share price from yfinance
- **Intrinsic Value (DCF)** — your model's estimate, colored green (undervalued) or red (overvalued) with % upside/downside
- **Enterprise Value** — total business value = PV(FCF) + PV(TV)
- **Equity Value** — what belongs to shareholders = EV − Net Debt

### FCF Chart
A combined bar + line chart (Chart.js):
- **Blue bars** — historical FCF (actual, from yfinance)
- **Green bars** — projected FCF (model output)
- **Yellow line** — discounted FCF (present value of each projected year's FCF)
- A **vertical dashed divider** separates historical from projected data
- A "PROJECTED →" label is drawn on the canvas

### Enterprise Value Bridge
Step-by-step arithmetic from PV(FCF) to intrinsic price per share, displayed as a vertical table:
```
Σ PV of Forecast FCFs     $XX.XXB
+ PV of Terminal Value    $XX.XXB
= Enterprise Value        $XX.XXB
− Net Debt                $XX.XXB
= Equity Value            $XX.XXB
÷ Diluted Shares          X.XXB
= Intrinsic Price         $XXX.XX
```
Below the bridge: a **Terminal Value disclosure box** showing TV as % of EV, with a contextual warning if TV > 70%.

### Financial Statements (3 tabs)

**Income Statement tab** — projected years, fully reconciled:
`Revenue → COGS → Gross Profit (with GP Margin %) → OpEx → EBIT (with EBIT Margin %) → NOPAT`

**Cash Flow tab** — FCF bridge for each projected year:
`NOPAT → +D&A → −CapEx → −ΔWC → FCF → Discount Factor → PV(FCF) → Cumulative PV`
ΔWC is colored red when it's an outflow (WC growing) and green when it's an inflow (WC shrinking).

**Historical tab** — actual data from yfinance (as-reported):
`Revenue, COGS, Gross Profit, EBIT, EBIT Margin, D&A, CapEx, FCF`
Useful for validating that the data pull worked correctly and understanding the historical context for the margins used in projection.

### Sensitivity Heatmap
7×7 grid of intrinsic prices across WACC (rows) and terminal growth rate (columns). Heatmap is anchored to current market price. A legend explains the color thresholds. The base case cell has a blue outline.

### Trailing Margin Bars
Horizontal bar chart showing all 7 margins used in the projection:
COGS/Rev, Gross Margin, OpEx/Rev, EBIT Margin, D&A/Rev, CapEx/Rev, WC/Rev. Bars are scaled so a 50% margin fills the bar completely.

### Assumptions Panel
12-cell grid showing every assumption used: all 6 user inputs + all 6 data-derived margins. Useful for documentation and transparency.

### Warnings
If yfinance could not find a specific financial statement row, a yellow warning box is shown at the bottom. Common examples: missing D&A for some tickers (reported differently), missing debt data for cash-heavy companies, inability to fetch current price.

---

## API Reference

### `POST /api/valuation`

**Request body:**

```json
{
  "ticker": "AAPL",
  "forecast_years": 5,
  "revenue_growth_rate": 0.08,
  "wacc": 0.10,
  "terminal_growth_rate": 0.025,
  "tax_rate": 0.21,
  "wacc_range": [0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13],
  "tgr_range":  [0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04]
}
```

**Validation rules (enforced by Pydantic):**
- `terminal_growth_rate` must be strictly less than `wacc`
- `forecast_years` must be between 1 and 10
- `wacc` must be between 1% and 50%
- `ticker` is normalized to uppercase

**Response (abbreviated):**

```json
{
  "summary": {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "current_price": 192.35,
    "intrinsic_price": 218.40,
    "upside_downside_pct": 0.1350,
    "enterprise_value_bn": 3241.20,
    "equity_value_bn": 3318.55,
    "net_debt_bn": -77.35,
    "shares_outstanding_bn": 15.20,
    "sum_pv_fcf_bn": 512.30,
    "terminal_value_bn": 4800.10,
    "pv_terminal_value_bn": 2728.90,
    "terminal_value_pct_of_ev": 0.842,
    "wacc": 0.10,
    "terminal_growth_rate": 0.025,
    "forecast_years": 5
  },
  "historical": [ ... ],
  "forecast":   [ ... ],
  "sensitivity": {
    "wacc_values": [0.07, 0.08, ...],
    "tgr_values":  [0.01, 0.015, ...],
    "prices": [[...], [...], ...],
    "base_wacc": 0.10,
    "base_tgr": 0.025
  },
  "assumptions": { ... },
  "warnings": []
}
```

### `GET /api/health`

Returns `{ "status": "ok" }`. Used to verify the server is running.

### `GET /`

Serves `frontend/index.html`.

---

## Design Decisions & Tradeoffs

These are the deliberate choices made in building this model and why. Being able to explain these clearly is part of what makes this project CV-worthy.

**1. Flat CAGR instead of time-varying growth rates**

A stage model (high growth → fade to terminal rate) is more realistic but requires more assumptions. A flat CAGR is defensible and transparent. The sensitivity table partially compensates by showing outcomes across different effective growth environments.

**2. WACC as a user input instead of computed from CAPM**

Computing WACC from first principles requires: an equity beta (which varies by lookback window and frequency), a market risk premium (which is debated, typically 4–7%), a risk-free rate (which changes daily), and a current cost of debt. Each of these is itself an assumption. Exposing WACC as a single user input makes the sensitivity analysis cleaner and the model easier to interrogate.

**3. Common-size margins instead of line-item absolute projections**

Projecting costs as % of revenue automatically scales them with business size, which is the correct behavior for most operating cost lines. Absolute projections would require separate assumptions for every cost item. The limitation is that some costs have fixed components (rent, minimum headcount) that don't scale perfectly with revenue — acknowledged in the limitations section.

**4. OpEx derived as `Gross Profit − EBIT` instead of independent margin**

This is a correctness fix. Independently projecting both a COGS margin and an EBIT margin produces an implicit OpEx that does not equal `Gross Profit − EBIT` in the projections. Deriving OpEx from history as `GP − EBIT` and then projecting its margin ensures the income statement always reconciles as an identity.

**5. Single-file HTML frontend**

No build step, no npm, no framework. Opens directly in a browser. Easy to deploy alongside FastAPI's static file serving. Chart.js loaded from CDN. All state is in memory — no localStorage (which is intentional given the ephemeral nature of a single valuation run).

**6. Sensitivity heatmap anchored to market price**

A heatmap anchored to the matrix's own min/max would show relative variation within the matrix but give no information about whether the stock is over or undervalued at *any* point in the matrix. Anchoring to market price gives each cell an honest, absolute signal.

---

## Known Limitations

These are real limitations — not excuses. Being transparent about model limitations is itself a sign of financial literacy.

| Limitation | Impact | Mitigation |
|---|---|---|
| Flat CAGR (no fade) | Overvalues high-growth companies in terminal year | Use conservative growth rate; check sensitivity table |
| Margins are backward-looking | Assumes mean reversion to historical cost structure | Review historical tab; manually adjust if business model is changing |
| WACC is user-input (not computed) | Model does not reflect current market conditions automatically | Use WACC range in sensitivity; cross-reference with CAPM estimate |
| No segment-level modeling | Cannot model businesses with very different division margins | Better suited to relatively homogeneous businesses |
| Working capital assumes fixed WC/Revenue ratio | Does not model seasonal patterns or one-off WC changes | Use historical tab to validate WC/Revenue is stable |
| yfinance data quality varies by ticker | Some tickers have incomplete or incorrectly labeled financial statement rows | Check the warnings panel; validate with official filings |
| Tax rate is user-input (not effective rate) | Statutory rate ≠ effective rate for many companies | Use the actual effective tax rate from the income statement |
| No minority interest or preferred shares adjustment | Can overstate equity value for companies with these items | For most large-caps this is immaterial |

---

## Glossary

For readers who are new to financial modeling.

**CAGR (Compound Annual Growth Rate)** — The constant annual growth rate that, when compounded over a period, produces the same total growth as the actual historical path. Example: if revenue grew from $100B to $146B over 4 years, the CAGR is `(146/100)^(1/4) − 1 = 9.9%`.

**Capital Expenditure (CapEx)** — Cash spent on acquiring or maintaining physical assets (property, plant, equipment). Appears as a negative number (outflow) in the cash flow statement. In the FCF formula, we subtract CapEx because it is real cash leaving the business that EBIT does not capture.

**Common-Size Analysis** — A method of expressing financial statement items as a percentage of revenue. Enables comparison across time periods and companies of different sizes, and provides the basis for margin-based projections.

**D&A (Depreciation & Amortization)** — A non-cash accounting charge that reduces EBIT but does not reduce cash. When computing FCF, we add D&A back to NOPAT because no cash actually left the business when this charge was recorded.

**DCF (Discounted Cash Flow)** — A valuation method that estimates the present value of all future cash flows a business is expected to generate, discounted at an appropriate rate to reflect risk and time value of money.

**EBIT (Earnings Before Interest and Taxes)** — Operating profit. Measures the earnings generated by the core business operations, before the cost of financing (interest) and taxes are subtracted.

**Enterprise Value (EV)** — The total value of a business, available to all capital providers (both debt and equity). `EV = PV(FCF) + PV(Terminal Value)`. It is the "pre-debt" value.

**Equity Value** — The value belonging to shareholders after debt holders are paid. `Equity Value = EV − Net Debt`.

**Free Cash Flow (FCF)** — The cash a business generates after paying for operations and investments. Unlike net income, FCF is not affected by accounting choices. It is what could theoretically be paid out to all investors.

**Gordon Growth Model** — A formula for valuing a stream of cash flows that grow at a constant rate forever: `TV = FCF × (1 + g) / (r − g)`. Also called the perpetuity growth model.

**Net Debt** — Total financial debt minus cash and cash equivalents. A company with more cash than debt has *negative* net debt (net cash), which increases equity value relative to EV.

**NOPAT (Net Operating Profit After Tax)** — EBIT taxed at the corporate rate. Represents what the business earns if it had no debt (unlevered). `NOPAT = EBIT × (1 − tax rate)`.

**Terminal Value (TV)** — The value of a business beyond the explicit forecast period, calculated as a growing perpetuity. Often represents the majority of Enterprise Value in a DCF.

**WACC (Weighted Average Cost of Capital)** — The blended required return for all capital providers. It is used as the discount rate in a DCF, reflecting both the riskiness of the business's cash flows and the cost of the capital used to finance it.

**Working Capital (WC)** — `Current Assets − Current Liabilities`. Represents the short-term operational liquidity of the business. An increase in WC is a use of cash (cash outflow); a decrease is a source of cash (cash inflow).

---

## License

MIT License. Use freely, with attribution appreciated.

---

*Built with Python, FastAPI, yfinance, and Chart.js. Financial data sourced from Yahoo Finance via the yfinance library. This tool is for educational and research purposes and does not constitute investment advice.*