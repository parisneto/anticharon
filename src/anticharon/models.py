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
class SiblingAlternative:
    """Sibling alternative model in the same family."""
    model: str
    price_1m: float
    relation: str
    price_diff_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "price_1m": round(self.price_1m, 5),
            "relation": self.relation,
            "price_diff_pct": round(self.price_diff_pct, 2)
        }


@dataclass
class ModelAnalytics:
    """Historical trajectory and profile analytics for a model."""
    profile: str
    badge: str
    trend_direction: str
    volatility_cv_pct: float
    price_min_30d: float
    price_max_30d: float
    change_vs_30d_pct: float
    trajectory_sparkline: str
    recommendation: str
    secondary_badge: Optional[str] = None
    sibling_alternatives: List[SiblingAlternative] = field(default_factory=list)
    history_vector: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "badge": self.badge,
            "secondary_badge": self.secondary_badge,
            "trend_direction": self.trend_direction,
            "volatility_cv_pct": round(self.volatility_cv_pct, 2),
            "price_min_30d": round(self.price_min_30d, 5),
            "price_max_30d": round(self.price_max_30d, 5),
            "change_vs_30d_pct": round(self.change_vs_30d_pct, 2),
            "trajectory_sparkline": self.trajectory_sparkline,
            "recommendation": self.recommendation,
            "sibling_alternatives": [s.to_dict() for s in self.sibling_alternatives],
            "history_vector": {k: round(v, 5) for k, v in self.history_vector.items()}
        }


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
    analytics: Optional[ModelAnalytics] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "model": self.model,
            "price_1m": round(self.price_1m, 5),
            "ma_7d": round(self.ma_7d, 5),
            "change_vs_7d_pct": round(self.change_vs_7d_pct, 2)
        }
        if self.analytics:
            data["analytics"] = self.analytics.to_dict()
        return data


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
class HermesIntegrationStatus:
    """Status of Hermes agent configuration detection and synchronization."""
    detected: bool
    source: Optional[str] = None
    method: str = "standalone"  # 'cli', 'file_grep', or 'standalone'
    models_count: int = 0
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "source": self.source,
            "method": self.method,
            "models_count": self.models_count,
            "warning": self.warning
        }


@dataclass
class TrackerResult:
    """Full execution output from the price tracker."""
    status: str
    timestamp: str
    prices_shortlist: List[ModelPrice] = field(default_factory=list)
    price_warnings: List[PriceWarning] = field(default_factory=list)
    fallback: bool = False
    error: Optional[str] = None
    storage_path: Optional[str] = None
    config_path: Optional[str] = None
    hermes_integration: Optional[HermesIntegrationStatus] = None
    analytics_mode: bool = False
    hints_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "status": self.status,
            "timestamp": self.timestamp,
            "data_source": "cached_history" if self.fallback else "live_api",
            "api_offline_fallback": self.fallback,
            "fallback": self.fallback,
            "prices_shortlist": [p.to_dict() for p in self.prices_shortlist],
            "priceWarnings": [w.to_dict() for w in self.price_warnings],
        }
        if self.analytics_mode:
            data["analytics_mode"] = True
        if self.hermes_integration:
            data["hermes_integration"] = self.hermes_integration.to_dict()
        if self.storage_path:
            data["storage_path"] = self.storage_path
        if self.config_path:
            data["config_path"] = self.config_path
        if self.hints_enabled:
            data["_hints"] = {
                "data_source": "'live_api' (fresh prices from OpenRouter) or 'cached_history' (offline fallback if API fails)",
                "api_offline_fallback": "True only if OpenRouter API failed and local CSV cache was used. Has NO relation to Hermes model fallback_providers.",
                "prices_shortlist": "Active models sorted cheapest to most expensive by blended price/1M tokens",
                "priceWarnings": "Alerts for price spikes, price drops, or when a model is cheaper than configured default",
                "hermes_integration": "Auto-sync status with ~/.hermes/config.yaml (models_count includes default + fallback_providers)"
            }
        if self.error:
            data["error"] = self.error
        return data


@dataclass
class PromptMixResult:
    """Result of prompt/completion ratio calculation from activity logs.

    `weight_prompt`/`weight_completion` are the legacy 2-way split (kept for
    backward compatibility with existing config/CLI consumers). The
    cache-aware 3-way split (`weight_uncached_prompt` + `weight_cached_prompt`
    + `weight_completion`) is the one ADR-2026-0002-TOKENS-CACHED formulas use.
    """
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    weight_prompt: float
    weight_completion: float
    records_count: int
    total_cached_tokens: int = 0
    total_uncached_tokens: int = 0
    weight_uncached_prompt: float = 0.0
    weight_cached_prompt: float = 0.0
    cache_hit_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records_count": self.records_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_uncached_tokens": self.total_uncached_tokens,
            "total_tokens": self.total_tokens,
            "weight_prompt": round(self.weight_prompt, 6),
            "weight_completion": round(self.weight_completion, 6),
            "weight_uncached_prompt": round(self.weight_uncached_prompt, 6),
            "weight_cached_prompt": round(self.weight_cached_prompt, 6),
            "cache_hit_rate": round(self.cache_hit_rate, 6),
            "prompt_pct": f"{self.weight_prompt * 100:.2f}%",
            "completion_pct": f"{self.weight_completion * 100:.2f}%"
        }
