"""Django signals emitted by cart operations.

Covers the five signals declared in cart.signals:
    cart_item_added, cart_item_removed, cart_item_updated,
    cart_checked_out, cart_cleared.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import Cart
from cart.signals import (
    cart_checked_out,
    cart_cleared,
    cart_item_added,
    cart_item_removed,
    cart_item_updated,
)


@pytest.fixture
def signal_sink():
    """Capture cart signal emissions for test inspection.

    Yields a dict with one list per signal name (``added``, ``removed``,
    ``updated``, ``checked_out``, ``cleared``). Each handler appends a
    record of the kwargs it was invoked with. Handlers are connected on
    setup and disconnected on teardown automatically.

    Example::

        def test_add_emits(cart, product, signal_sink):
            cart.add(product, Decimal("5.00"))
            assert len(signal_sink["added"]) == 1
    """
    captured = {
        "added": [],
        "removed": [],
        "updated": [],
        "checked_out": [],
        "cleared": [],
    }

    def on_added(sender, cart, item, **kwargs):
        captured["added"].append({"cart": cart, "item": item})

    def on_removed(sender, cart, product, **kwargs):
        captured["removed"].append({"cart": cart, "product": product})

    def on_updated(sender, cart, item, **kwargs):
        captured["updated"].append(
            {
                "cart": cart,
                "item": item,
                "deleted": kwargs.get("deleted", False),
            }
        )

    def on_checked_out(sender, cart, **kwargs):
        captured["checked_out"].append({"cart": cart})

    def on_cleared(sender, cart, **kwargs):
        captured["cleared"].append({"cart": cart})

    cart_item_added.connect(on_added, sender=Cart)
    cart_item_removed.connect(on_removed, sender=Cart)
    cart_item_updated.connect(on_updated, sender=Cart)
    cart_checked_out.connect(on_checked_out, sender=Cart)
    cart_cleared.connect(on_cleared, sender=Cart)

    yield captured

    cart_item_added.disconnect(on_added, sender=Cart)
    cart_item_removed.disconnect(on_removed, sender=Cart)
    cart_item_updated.disconnect(on_updated, sender=Cart)
    cart_checked_out.disconnect(on_checked_out, sender=Cart)
    cart_cleared.disconnect(on_cleared, sender=Cart)


# --------------------------------------------------------------------------- #
# cart_item_added
# --------------------------------------------------------------------------- #


def test_cart_item_added_fires_on_add(cart, product, signal_sink):
    item = cart.add(product, unit_price=Decimal("9.99"), quantity=2)

    assert len(signal_sink["added"]) == 1
    assert signal_sink["added"][0]["cart"] == cart.cart
    assert signal_sink["added"][0]["item"] == item


def test_cart_item_added_fires_again_on_repeat_add(cart, product, signal_sink):
    cart.add(product, unit_price=Decimal("9.99"), quantity=2)
    cart.add(product, unit_price=Decimal("9.99"), quantity=1)

    assert len(signal_sink["added"]) == 2


# --------------------------------------------------------------------------- #
# cart_item_removed
# --------------------------------------------------------------------------- #


def test_cart_item_removed_fires_on_remove(cart, product, signal_sink):
    cart.add(product, unit_price=Decimal("9.99"), quantity=2)

    cart.remove(product)

    assert len(signal_sink["removed"]) == 1
    assert signal_sink["removed"][0]["cart"] == cart.cart
    assert signal_sink["removed"][0]["product"] == product


# --------------------------------------------------------------------------- #
# cart_item_updated
# --------------------------------------------------------------------------- #


def test_cart_item_updated_fires_on_update(cart, product, signal_sink):
    cart.add(product, unit_price=Decimal("9.99"), quantity=2)

    cart.update(product, quantity=5, unit_price=Decimal("11.99"))

    assert len(signal_sink["updated"]) == 1
    assert signal_sink["updated"][0]["cart"] == cart.cart
    assert signal_sink["updated"][0]["deleted"] is False


def test_cart_item_updated_carries_deleted_flag_on_zero_quantity(
    cart, product, signal_sink
):
    cart.add(product, unit_price=Decimal("9.99"), quantity=2)

    cart.update(product, quantity=0)

    assert len(signal_sink["updated"]) == 1
    assert signal_sink["updated"][0]["deleted"] is True


# --------------------------------------------------------------------------- #
# cart_checked_out
# --------------------------------------------------------------------------- #


def test_cart_checked_out_fires_on_checkout(cart, product, signal_sink):
    cart.add(product, unit_price=Decimal("1.00"))
    cart.checkout()

    assert len(signal_sink["checked_out"]) == 1
    assert signal_sink["checked_out"][0]["cart"] == cart.cart


# --------------------------------------------------------------------------- #
# cart_cleared
# --------------------------------------------------------------------------- #


def test_cart_cleared_fires_on_clear(cart, product, signal_sink):
    cart.add(product, unit_price=Decimal("9.99"), quantity=2)

    cart.clear()

    assert len(signal_sink["cleared"]) == 1
    assert signal_sink["cleared"][0]["cart"] == cart.cart
