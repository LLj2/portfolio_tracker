import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from typing import List
from . import db, schemas, performance, rebalancing
from .ingest import csv_import
from .providers import pricing, scheduler_jobs

# Configure structured logging
import json
from datetime import datetime

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                          'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
                          'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'message']:
                log_entry[key] = value

        return json.dumps(log_entry)

# Set up structured logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(message)s",
    handlers=[logging.StreamHandler()]
)

# Apply structured formatter to root logger
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.setFormatter(StructuredFormatter())

logger = logging.getLogger(__name__)

app = FastAPI(title="Portfolio Backend (MVP)")

# CORS configuration from environment
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
allowed_origins = [origin.strip() for origin in allowed_origins]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    try:
        db.init_db()
        scheduler_jobs.start_scheduler(pricing)
        logger.info("Application started successfully")
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise

@app.on_event("shutdown")
def on_shutdown():
    try:
        scheduler_jobs.shutdown_scheduler()
        logger.info("Application shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint for Docker and monitoring"""
    try:
        # Test database connectivity
        with db.SessionLocal() as s:
            s.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "service": "portfolio-tracker",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail={
            "status": "unhealthy",
            "service": "portfolio-tracker",
            "database": "disconnected",
            "error": str(e)
        })

# Accounts
@app.post("/accounts", response_model=schemas.AccountOut)
def create_account(acc: schemas.AccountCreate):
    try:
        with db.SessionLocal() as s:
            obj = db.create_account(s, acc)
            return obj
    except SQLAlchemyError as e:
        logger.error(f"Database error creating account: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    except Exception as e:
        logger.error(f"Unexpected error creating account: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Uploads
@app.post("/upload/holdings")
async def upload_holdings_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file.")
    
    # Limit file size (10MB)
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max size: 10MB")
    
    try:
        content = (await file.read()).decode("utf-8")
        if not content.strip():
            raise HTTPException(400, "Empty file")
            
        with db.SessionLocal() as s:
            cnt = csv_import.import_holdings_csv(s, content)
            s.commit()
            logger.info(f"Imported {cnt} holdings records")
        return {"status": "ok", "rows": cnt}
    except UnicodeDecodeError:
        raise HTTPException(400, "Invalid file encoding. Please use UTF-8")
    except SQLAlchemyError as e:
        logger.error(f"Database error importing holdings: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    except Exception as e:
        logger.error(f"Error importing holdings: {e}")
        raise HTTPException(status_code=500, detail="Import failed")

@app.post("/upload/nav")
async def upload_nav_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file.")
    
    # Limit file size (10MB)
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max size: 10MB")
    
    try:
        raw_content = await file.read()
        # Try UTF-8 first, then fallback to common encodings
        for encoding in ['utf-8', 'utf-8-sig', 'windows-1252', 'iso-8859-1']:
            try:
                content = raw_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise HTTPException(400, "Cannot decode file. Please save as UTF-8")
        
        if not content.strip():
            raise HTTPException(400, "Empty file")
            
        with db.SessionLocal() as s:
            cnt = csv_import.import_nav_csv(s, content)
            s.commit()
            logger.info(f"Imported {cnt} NAV records")
        return {"status": "ok", "rows": cnt}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error importing NAV: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    except Exception as e:
        logger.error(f"Error importing NAV: {e}")
        raise HTTPException(status_code=500, detail="Import failed")

# Manual price refresh
@app.post("/admin/refresh/prices")
def refresh_prices():
    try:
        with db.SessionLocal() as s:
            pricing.run_price_cycle(s)
            s.commit()
            logger.info("Manual price refresh completed")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error refreshing prices: {e}")
        raise HTTPException(status_code=500, detail="Price refresh failed")

# Manual snapshot capture
@app.post("/admin/snapshot")
def capture_snapshot():
    try:
        with db.SessionLocal() as s:
            performance.capture_eod_snapshots(s)
            s.commit()
            logger.info("Manual snapshot captured")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error capturing snapshot: {e}")
        raise HTTPException(status_code=500, detail="Snapshot capture failed")

# Portfolio
@app.get("/portfolio/latest", response_model=schemas.PortfolioOverview)
def portfolio_latest():
    try:
        with db.SessionLocal() as s:
            return performance.latest_overview(s, base_ccy=os.getenv("BASE_CURRENCY","EUR"))
    except Exception as e:
        logger.error(f"Error getting latest portfolio: {e}")
        raise HTTPException(status_code=500, detail="Failed to get portfolio data")

@app.get("/portfolio/history", response_model=schemas.PortfolioHistory)
def portfolio_history():
    try:
        with db.SessionLocal() as s:
            return performance.history(s)
    except Exception as e:
        logger.error(f"Error getting portfolio history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get portfolio history")

@app.get("/portfolio/positions", response_model=List[schemas.PositionDetail])
def portfolio_positions():
    try:
        with db.SessionLocal() as s:
            return performance.get_positions(s)
    except Exception as e:
        logger.error(f"Error getting portfolio positions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get portfolio positions")

@app.get("/portfolio/positions/export")
def export_positions_csv():
    """Export all positions as a CSV file with P&L data."""
    import csv
    import io
    from datetime import datetime as dt

    try:
        with db.SessionLocal() as s:
            positions = performance.get_positions(s)

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Name", "Code", "Asset Class", "Type", "Account", "Currency",
            "Quantity", "Price (EUR)", "Value (EUR)", "Cost Basis (EUR)",
            "Unrealized P&L (EUR)", "P&L %", "Weight %", "Freshness",
        ])
        for p in positions:
            writer.writerow([
                p.name, p.code, p.asset_class, p.instrument_type, p.account,
                p.currency, p.quantity, round(p.price_eur, 2),
                round(p.value_eur, 2), round(p.cost_basis_eur, 2),
                round(p.unrealized_pnl, 2), round(p.pnl_percentage, 2),
                round(p.weight * 100, 2), p.freshness,
            ])

        buf.seek(0)
        filename = f"holdings_{dt.now().strftime('%Y%m%d_%H%M')}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"Error exporting positions: {e}")
        raise HTTPException(status_code=500, detail="Failed to export positions")

# Policy & Rebalance
@app.get("/policy", response_model=schemas.PolicyIn)
def get_policy():
    try:
        with db.SessionLocal() as s:
            policy = db.get_policy(s)
            if not policy:
                raise HTTPException(404, "No policy configured.")
            return policy
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting policy: {e}")
        raise HTTPException(status_code=500, detail="Failed to get policy")

@app.post("/policy")
def set_policy(policy: schemas.PolicyIn):
    try:
        with db.SessionLocal() as s:
            db.set_policy(s, policy)
            s.commit()
            logger.info("Policy updated")
        return {"status":"ok"}
    except Exception as e:
        logger.error(f"Error setting policy: {e}")
        raise HTTPException(status_code=500, detail="Failed to set policy")

@app.get("/rebalance", response_model=schemas.RebalanceOut)
def get_rebalance():
    try:
        with db.SessionLocal() as s:
            logger.info("Getting latest portfolio overview...")
            latest = performance.latest_overview(s, base_ccy=os.getenv("BASE_CURRENCY","EUR"))
            logger.info(f"Portfolio overview: {latest}")
            
            logger.info("Getting policy...")
            policy = db.get_policy(s)
            logger.info(f"Policy result: {policy}")
            
            if not policy:
                logger.warning("No policy found in database")
                raise HTTPException(400, "No policy set.")
            
            logger.info("Calling suggest_trades...")
            result = rebalancing.suggest_trades(latest, policy)
            logger.info(f"Rebalance suggestions: {result}")
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting rebalance suggestions: {e}")
        logger.error(f"Exception type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get rebalance suggestions: {str(e)}")

# Static file serving for frontend
# Mount static files directory (if it exists)
static_dir = "/app/frontend"
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def read_index():
        """Serve the main frontend HTML file"""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Portfolio Tracker API", "docs": "/docs"}
else:
    @app.get("/")
    def api_root():
        return {"message": "Portfolio Tracker API", "docs": "/docs"}
