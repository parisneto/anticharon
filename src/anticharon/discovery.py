"""Model catalog discovery and multi-criteria exploration engine."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from anticharon.pricing import is_valid_listed_price
from anticharon.tracker import OPENROUTER_MODELS_URL


@dataclass
class CatalogModel:
    """Structured representation of an OpenRouter catalog model."""
    id: str
    name: str
    context_length: int
    prompt_price_1m: float
    completion_price_1m: float
    blended_price_1m: float
    is_promo: bool
    output_modalities: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "context_length": self.context_length,
            "prompt_price_1m": round(self.prompt_price_1m, 6),
            "completion_price_1m": round(self.completion_price_1m, 6),
            "blended_price_1m": round(self.blended_price_1m, 6),
            "is_promo": self.is_promo,
            "output_modalities": self.output_modalities,
            "description": self.description
        }


def fetch_catalog(
    timeout: float = 10.0,
    weight_prompt: float = 0.9971,
    weight_completion: float = 0.0029
) -> List[CatalogModel]:
    """Fetch and parse all models from OpenRouter API."""
    try:
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=timeout)
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", [])
    except Exception:
        return []

    catalog: List[CatalogModel] = []
    for item in data:
        model_id = item.get("id", "")
        if not model_id:
            continue

        name = item.get("name", model_id)
        ctx = item.get("context_length") or 0
        desc = item.get("description") or ""

        # Modalities
        arch = item.get("architecture") or {}
        output_modalities = arch.get("output_modalities") or ["text"]

        # Pricing per 1M tokens
        pricing = item.get("pricing") or {}
        try:
            p_in = float(pricing.get("prompt", 0)) * 1_000_000
            p_out = float(pricing.get("completion", 0)) * 1_000_000
        except (ValueError, TypeError):
            p_in, p_out = 0.0, 0.0

        if not (is_valid_listed_price(p_in) and is_valid_listed_price(p_out)):
            # Sentinel/non-priced model (e.g. a meta-router like openrouter/auto-beta) --
            # skip rather than let a negative sentinel masquerade as "cheapest".
            continue

        blended = (p_in * weight_prompt) + (p_out * weight_completion)

        # Promo / Discount detection
        is_promo = (
            ":free" in model_id.lower()
            or "(free)" in name.lower()
            or p_in == 0.0
            or "discount" in model_id.lower()
        )

        catalog.append(CatalogModel(
            id=model_id,
            name=name,
            context_length=ctx,
            prompt_price_1m=p_in,
            completion_price_1m=p_out,
            blended_price_1m=blended,
            is_promo=is_promo,
            output_modalities=output_modalities,
            description=desc
        ))

    return catalog


def filter_catalog(
    models: List[CatalogModel],
    query: Optional[str] = None,
    promo_only: bool = False,
    modality: Optional[str] = "text",
    max_price: Optional[float] = None,
    max_input_price: Optional[float] = None,
    max_output_price: Optional[float] = None,
    filter_expressions: Optional[List[str]] = None
) -> List[CatalogModel]:
    """Filter catalog models using multi-criteria keywords, modality, and price inequalities."""
    results = models

    # 1. Modality filter (e.g. text)
    if modality:
        mod_lower = modality.lower().strip()
        results = [m for m in results if any(mod_lower in om.lower() for om in m.output_modalities)]

    # 2. Promo / Discount filter
    if promo_only:
        results = [m for m in results if m.is_promo]

    # 3. Main positional search query
    if query:
        q_lower = query.lower().strip()
        results = [
            m for m in results
            if q_lower in m.id.lower()
            or q_lower in m.name.lower()
            or q_lower in m.description.lower()
        ]

    # 4. Direct price filters
    if max_price is not None:
        results = [m for m in results if m.blended_price_1m <= max_price]

    if max_input_price is not None:
        results = [m for m in results if m.prompt_price_1m <= max_input_price]

    if max_output_price is not None:
        results = [m for m in results if m.completion_price_1m <= max_output_price]

    # 5. Generic filter expressions (e.g. "openai", "price < 10", "input < 3.50", "output < 15")
    if filter_expressions:
        for expr in filter_expressions:
            expr_clean = expr.strip()

            # Check for inequality expressions: e.g. "price < 10", "input < 3.50", "output <= 5.0"
            price_match = re.match(r"^(price|input|output)\s*([<>]=?)\s*([0-9.]+)\s*$", expr_clean, re.IGNORECASE)
            if price_match:
                target_type = price_match.group(1).lower()
                op = price_match.group(2)
                val = float(price_match.group(3))

                def check_inequality(val_to_test: float) -> bool:
                    if op == "<":
                        return val_to_test < val
                    elif op == "<=":
                        return val_to_test <= val
                    elif op == ">":
                        return val_to_test > val
                    elif op == ">=":
                        return val_to_test >= val
                    return True

                if target_type == "price":
                    results = [m for m in results if check_inequality(m.blended_price_1m)]
                elif target_type == "input":
                    results = [m for m in results if check_inequality(m.prompt_price_1m)]
                elif target_type == "output":
                    results = [m for m in results if check_inequality(m.completion_price_1m)]
            else:
                # Treat as keyword search
                kw = expr_clean.lower()
                results = [
                    m for m in results
                    if kw in m.id.lower() or kw in m.name.lower() or kw in m.description.lower()
                ]

    # Sort results by blended price (cheapest first)
    results.sort(key=lambda m: m.blended_price_1m)
    return results


def format_discovery_output(models: List[CatalogModel], json_mode: bool = False) -> None:
    """Format and print discovered catalog models."""
    if json_mode:
        payload = {
            "status": "success",
            "count": len(models),
            "models": [m.to_dict() for m in models]
        }
        print(json.dumps(payload, indent=2))
        return

    print("\n" + "=" * 90)
    print(f"🔍 ANTICHARON — OpenRouter Model Discovery (Found: {len(models)} models)")
    print("=" * 90)

    if not models:
        print("  No models matched your search or filter criteria.")
        print("=" * 90 + "\n")
        return

    print(f"{'MODEL ID':<42} {'CONTEXT':<12} {'INPUT/1M':<10} {'OUTPUT/1M':<11} {'BLENDED/1M':<11} {'PROMO'}")
    print("-" * 90)

    for m in models:
        ctx_str = f"{m.context_length:,}" if m.context_length > 0 else "-"
        promo_badge = "🎁 [FREE/PROMO]" if m.is_promo else "-"
        print(
            f"{m.id:<42} {ctx_str:<12} ${m.prompt_price_1m:<9.5f} ${m.completion_price_1m:<10.5f} ${m.blended_price_1m:<10.5f} {promo_badge}"
        )

    print("-" * 90)
    print(f"Total matching models: {len(models)} (Sorted by lowest blended cost/1M tokens)")
    print("=" * 90 + "\n")
