from decimal import Decimal, ROUND_HALF_UP

Q=Decimal("0.001")
def calculate_member_premium(policy, plan, effective_date, end_date=None):
    if not policy.premium_calculation_enabled: return Decimal("0.000"), {"method":"DISABLED"}
    cfg=plan.premium_configuration or {}
    method=cfg.get("method","PRORATA")
    annual=plan.annual_premium or Decimal("0")
    if method=="FULL": amount=annual; snap={"method":"FULL","annual":str(annual)}
    elif method=="LUMP_SUM":
        amount=Decimal(str(cfg.get("amount","0"))); snap={"method":"LUMP_SUM","amount":str(amount)}
    elif method=="PARTIAL":
        factor=Decimal(str(cfg.get("factor","1"))); amount=annual*factor; snap={"method":"PARTIAL","annual":str(annual),"factor":str(factor)}
    else:
        finish=end_date or policy.expiry_date
        covered=max((finish-effective_date).days+1,0)
        denominator=Decimal(str(cfg.get("denominator",(policy.expiry_date-policy.start_date).days+1)))
        amount=annual*Decimal(covered)/denominator if denominator else Decimal("0")
        snap={"method":"PRORATA","annual":str(annual),"covered_days":covered,"denominator":str(denominator)}
    amount=amount.quantize(Q, rounding=ROUND_HALF_UP); snap["calculated_amount"]=str(amount)
    return amount,snap
