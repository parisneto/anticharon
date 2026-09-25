"""Shared MCP and CLI prompt templates."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """Prompt metadata and renderer shared by all user surfaces."""

    name: str
    description: str
    render: Callable[..., str]


def cost_spike_triage(model_id: str, current_price: float, ma_7d: float) -> str:
    return (
        f"Anticharon detected a significant price increase on model '{model_id}'.\n"
        f"Current Price per 1M tokens: ${current_price:.5f}\n"
        f"7-Day Moving Average: ${ma_7d:.5f}\n\n"
        "Please analyze this price jump:\n"
        "1. Check if an introductory promotion ended or vendor raised rates.\n"
        "2. Use tool `discover_models` or `check_prices` to identify cheaper alternatives in the same family.\n"
        "3. Recommend whether to switch Hermes default model or reorder fallback_providers."
    )


def model_migration_advisor(legacy_model: str, recommended_model: str) -> str:
    return (
        f"Anticharon flagged model '{legacy_model}' with a SUNSETTING profile.\n"
        f"A newer version in the same model family ('{recommended_model}') is available at an equal or lower cost.\n\n"
        "Please formulate an action plan:\n"
        f"1. Compare performance characteristics of '{recommended_model}' vs '{legacy_model}'.\n"
        f"2. Validate that '{recommended_model}' is compatible with active agent tool schemas.\n"
        f'3. Provide the exact Hermes CLI command to switch the default model: `hermes config set model.default "{recommended_model}"`.'
    )


def family_upgrade_discover(model_or_family: str) -> str:
    return (
        f"Anticharon agent workflow: Discover newer version models in family '{model_or_family}'.\n\n"
        "Execution Plan:\n"
        f'1. Run tool `discover_models(query="{model_or_family}")` to find all active catalog models in this family.\n'
        "2. Identify newer generations or sibling variants (e.g. 3.8 vs 3.7, flash vs flash-lite, coder vs chat).\n"
        "3. Compare calibrated blended pricing per 1M tokens against current rates.\n"
        "4. If a newer model is cheaper or equal in cost, formulate an upgrade recommendation:\n"
        "   - Compare context windows and benchmark strengths.\n"
        f'   - Provide the CLI command: `hermes config set model.default "<new_model_slug>"`.\n'
        f'   - Offer to add it to shortlist: `anticharon model add "<new_model_slug>"`.'
    )


def daily_cost_briefing(budget_threshold: float = 0.50) -> str:
    return (
        f"Anticharon agent workflow: Executive Daily Cost Briefing (Threshold: ${budget_threshold:.2f}/1M tokens).\n\n"
        "Execution Plan:\n"
        "1. Call tool `check_prices()` (run `run_prices()` first if it reports `DATA_STALE`).\n"
        "2. Check for any active price warnings (e.g. `BEST_OPTION_CHANGED`, `PRICE_SPIKE`, `PRICE_DROP`).\n"
        f"3. Identify models exceeding ${budget_threshold:.2f} per 1M blended tokens.\n"
        "4. Produce a concise 3-bullet briefing:\n"
        "   • 🏆 Cheapest Workhorse Model right now\n"
        "   • ⚠️ Volatility & Alerts (spikes, expired promos, or default model surpassed)\n"
        "   • 💡 Actionable Recommendation for today's LLM agent orchestration"
    )


def budget_optimization_audit() -> str:
    return (
        "Anticharon agent workflow: Comprehensive Shortlist Budget Audit.\n\n"
        "Execution Plan:\n"
        "1. Call tool `get_model_history()` to inspect 30-day trajectories and intelligence profiles.\n"
        "2. Classify models by budget tier:\n"
        "   - Identify models classified as 🛡️ STABLE (low budget risk).\n"
        "   - Flag models classified as 📈 PROMO_ENDED or ⚠️ SUNSETTING.\n"
        "   - Flag models with high CV% volatility (⚡ VOLATILE).\n"
        "3. For any expensive or sunsetting model, run `discover_models` to find drop-in replacements.\n"
        "4. Recommend optimal Hermes `fallback_providers` ordering (cheapest reliable providers first)."
    )


PROMPTS = {
    prompt.name: prompt
    for prompt in (
        Prompt("cost_spike_triage", "Guidance for evaluating a PRICE_SPIKE or PROMO_ENDED alert and recommending cheaper models.", cost_spike_triage),
        Prompt("model_migration_advisor", "Guidance for evaluating a SUNSETTING model profile and migrating to a newer sibling model.", model_migration_advisor),
        Prompt("family_upgrade_discover", "Discovers newer generation models in the same provider family and evaluates cost-benefit migration.", family_upgrade_discover),
        Prompt("daily_cost_briefing", "Generates an executive daily cost briefing of model prices, moving averages, and volatility alerts across the active shortlist.", daily_cost_briefing),
        Prompt("budget_optimization_audit", "Audits the active shortlist to identify cost outliers, SUNSETTING legacy versions, and opportunities to reorder fallback providers.", budget_optimization_audit),
    )
}


def render_prompt(name: str, arguments: dict[str, str] | None = None) -> str:
    """Render a named prompt from supplied CLI key/value arguments."""
    try:
        prompt = PROMPTS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown prompt '{name}'. Available prompts: {', '.join(PROMPTS)}") from exc
    import inspect

    signature = inspect.signature(prompt.render)
    values = dict(arguments or {})
    unknown = values.keys() - signature.parameters.keys()
    if unknown:
        raise ValueError(f"Unknown argument(s) for {name}: {', '.join(sorted(unknown))}")
    converted = {}
    for key, parameter in signature.parameters.items():
        if key in values:
            converted[key] = float(values[key]) if parameter.annotation is float else values[key]
        elif parameter.default is not inspect.Parameter.empty:
            converted[key] = parameter.default
        else:
            raise ValueError(f"Missing required argument '{key}' for prompt '{name}'")
    return prompt.render(**converted)
