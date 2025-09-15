from pydantic import BaseModel
from typing import List, Dict

class AccountCreate(BaseModel):
    name: str
    institution: str
    currency: str = "EUR"

class AccountOut(BaseModel):
    id: int
    name: str
    institution: str
    currency: str
    class Config:
        from_attributes = True

class PolicyTargetIn(BaseModel):
    asset_class: str
    weight: float
    band: float

class PolicyIn(BaseModel):
    base_currency: str = "EUR"
    targets: List[PolicyTargetIn]

class SleeveWeight(BaseModel):
    asset_class: str
    value: float
    weight: float
    freshness: str

class PositionDetail(BaseModel):
    name: str
    code: str
    asset_class: str
    account: str
    quantity: float
    price_eur: float
    value_eur: float
    weight: float
    freshness: str
    currency: str

class PortfolioOverview(BaseModel):
    total_value: float
    by_sleeve: List[SleeveWeight]
    drift: Dict[str, float]

class HistoryPoint(BaseModel):
    ts: str
    total_value_eur: float

class PortfolioHistory(BaseModel):
    points: List[HistoryPoint]

class TradeSuggestion(BaseModel):
    asset_class: str
    action: str
    amount: float

class RebalanceOut(BaseModel):
    hard_drift: List[str]
    suggestions: List[TradeSuggestion]
