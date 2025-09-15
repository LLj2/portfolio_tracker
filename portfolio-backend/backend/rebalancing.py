from typing import List
from .schemas import PortfolioOverview, PolicyIn, TradeSuggestion, RebalanceOut

def suggest_trades(overview: PortfolioOverview, policy: PolicyIn) -> RebalanceOut:
    """
    Generate rebalancing suggestions based on current portfolio vs policy targets.
    
    Returns suggestions for asset classes that have drifted beyond their bands.
    """
    hard_drift = []
    suggestions = []
    
    # Build policy targets lookup
    policy_targets = {t.asset_class: t for t in policy.targets}
    
    for sleeve in overview.by_sleeve:
        asset_class = sleeve.asset_class
        current_weight = sleeve.weight
        
        if asset_class not in policy_targets:
            continue
            
        target = policy_targets[asset_class]
        target_weight = target.weight
        band = target.band
        drift = current_weight - target_weight
        
        # Check if drift exceeds band (hard drift)
        if abs(drift) > band:
            hard_drift.append(asset_class)
            
            # Calculate trade amount needed to get back to target
            target_value = overview.total_value * target_weight
            current_value = sleeve.value
            trade_amount = target_value - current_value
            
            action = "BUY" if trade_amount > 0 else "SELL"
            suggestions.append(TradeSuggestion(
                asset_class=asset_class,
                action=action,
                amount=abs(trade_amount)
            ))
    
    return RebalanceOut(
        hard_drift=hard_drift,
        suggestions=suggestions
    )