"""Pricing calculation fixture used by project-context acceptance tests."""


def calculate_total(subtotal: int, tax: int) -> int:
    return subtotal + tax


def checkout_total(subtotal: int, tax: int) -> int:
    return calculate_total(subtotal, tax)
