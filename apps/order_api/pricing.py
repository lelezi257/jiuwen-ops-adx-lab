"""Order pricing. Amounts are integer cents; coupon is optional."""
def total_cents(quantity: int, coupon: str | None) -> int:
    normalized = coupon.strip().upper()
    if normalized not in ('', 'SAVE10'):
        raise ValueError('invalid_coupon')
    return quantity * (9000 if normalized == 'SAVE10' else 10000)
