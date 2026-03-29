"""
Django signals for cart operations.
"""

from django.dispatch import Signal

cart_item_added = Signal()
cart_item_removed = Signal()
cart_item_updated = Signal()
cart_checked_out = Signal()
cart_cleared = Signal()
