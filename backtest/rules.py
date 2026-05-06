import re

COMMISSION_RULES = {
    "I": {"type": "prop", "value": 0.0001},
    "P": {"type": "fixed", "value": 2.5},
    "AU": {"type": "fixed", "value": 10.0},
    "AG": {"type": "prop", "value": 0.00005},
    "CU": {"type": "prop", "value": 0.00005},
    "M": {"type": "fixed", "value": 1.5},
    "SC": {"type": "fixed", "value": 20.0},
}

MARGIN_RULES = {
    "I": 0.15,
    "P": 0.10,
    "AU": 0.08,
    "AG": 0.12,
    "CU": 0.10,
    "M": 0.08,
    "SC": 0.15,
}

def get_margin_rate(symbol: str) -> float:
    """获取合约的保证金率。股票强制 100%，期货按照规则或默认 10%。"""
    if symbol.endswith((".SH", ".SZ", ".BJ")):
        return 1.0
    
    match = re.match(r"^([a-zA-Z]+)", symbol)
    if match:
        product = match.group(1).upper()
        return MARGIN_RULES.get(product, 0.10)
    
    return 1.0

def calculate_commission(
    symbol: str, price: float, quantity: float, multiplier: float, rate: float
) -> float:
    if rate >= 0:
        # Generic proportional logic: rate * notional value
        return price * quantity * multiplier * rate
        
    # rule-based (rate < 0)
    match = re.match(r"^([a-zA-Z]+)", symbol)
    if not match:
        return 0.0
        
    product = match.group(1).upper()
    rule = COMMISSION_RULES.get(product)
    
    if not rule:
        return 0.0
        
    if rule["type"] == "fixed":
        return quantity * rule["value"]
    elif rule["type"] == "prop":
        return price * quantity * multiplier * rule["value"]
        
    return 0.0
