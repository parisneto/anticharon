"""Data models and type definitions for Anticharon."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class PriceRecord:
    """Historical price record for a single model in CSV."""
    model: str
    last_updated: str
    current: float
    ma_3d: float
    ma_7d: float
    prices: List[float]  # 9-element array: [d1, d2, d3, d4, d5, d6, d7, d15, d30]


@dataclass
class ModelPrice:
    """Calculated current price and moving average metrics for a model."""
    model: str
    price_1m: float
    ma_7d: float
    change_vs_7d_pct: float
    ma_3d: Optional[float] = None
    prompt_price_raw: Optional[float] = None
    completion_price_raw: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "price_1m": round(self.price_1m, 5),
            "ma_7d": round(self.ma_7d, 5),
            "change_vs_7d_pct": round(self.change_vs_7d_pct, 2)
        }


@dataclass
class PriceWarning:
    """Warning structure for volatility or cheapest model alerts."""
    type: str  # 'PRICE_SPIKE', 'PRICE_DROP', 'BEST_OPTION_CHANGED'
    message: str
    model: Optional[str] = None
    current_default: Optional[str] = None
    suggested_cheapest: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "type": self.type,
            "message": self.message
        }
        if self.model:
            data["model"] = self.model
        if self.current_default:
            data["current_default"] = self.current_default
        if self.suggested_cheapest:
            data["suggested_cheapest"] = self.suggested_cheapest
        return data


@dataclass
class TrackerResult:
    """Full execution output from the price tracker."""
    status: str
    timestamp: str
    prices_shortlist: List[ModelPrice] = field(default_factory=list)
    price_warnings: List[PriceWarning] = field(default_factory=list)
    fallback: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "fallback": self.fallback,
            "prices_shortlist": [p.to_dict() for p in self.prices_shortlist],
            "priceWarnings": [w.to_dict() for w in self.price_warnings],
            **({"error": self.error} if self.error else {})
        }


@dataclass
class PromptMixResult:
    """Result of prompt/completion ratio calculation from activity logs."""
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    weight_prompt: float
    weight_completion: float
    records_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records_count": self.records_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "weight_prompt": round(self.weight_prompt, 6),
            "weight_completion": round(self.weight_completion, 6),
            "prompt_pct": f"{self.weight_prompt * 100:.2f}%",
            "completion_pct": f"{self.weight_completion * 100:.2f}%"
        }
