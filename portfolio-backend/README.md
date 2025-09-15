# Portfolio Backend — FastAPI + Scheduler (MVP)

Self‑hosted backend to:
- Load holdings (CSV for non‑Degiro; Degiro adapter later)
- Auto‑pull prices on a schedule (Crypto: CoinGecko; FX: ECB; Listed: placeholder)
- Store end‑of‑day (EOD) snapshots
- Expose APIs for latest valuation, history, and rebalancing

## Quickstart
1) Install Docker + Docker Compose
2) In the repo root:
   cp .env.example .env
   docker compose up --build
3) Open http://localhost:8000/docs

## Uploads (manual sources)
- POST /upload/holdings — CSV with columns:
  account,name,isin_or_symbol,asset_class,currency,quantity,book_cost
  • asset_class ∈ {Equity, Bonds, Fund, Crypto, Commodity, Lending, Cash, Other}
  • book_cost is OPTIONAL; leave blank if unknown
  • Crypto:  CRYPTO:BTC, CRYPTO:ETH, ...
  • Lending: LEND:<custom>
- POST /upload/nav — CSV (funds/lending NAV):
  date,isin_or_symbol,nav,currency

## Pricing & Scheduler
- Scheduler windows: env `SCHED_WINDOWS` (e.g., "12:00,20:00")
- EOD snapshots: env `SCHED_EOD_TIME` (e.g., "23:30")
- FX daily: env `SCHED_ECB_TIME` (ECB feed)
- Manual refresh: POST /admin/refresh/prices

## Portfolio APIs
- GET /portfolio/latest   → total value, sleeve breakdown, drift
- GET /portfolio/history  → equity curve points
- POST /policy            → set targets + bands
- GET /rebalance          → sleeve‑level suggestions when drift > band

## Notes
- Prices for listed equities/ETFs are a placeholder; swap in your preferred paid source.
- All values are normalized to EUR using the latest ECB FX.
- EOD snapshots keep a clean historical curve regardless of intraday quote gaps.
