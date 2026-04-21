from django.contrib import admin

from .models import Cart, Item


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0
    readonly_fields = ("content_type", "object_id", "unit_price", "quantity")

    @admin.display(description="Total")
    def total_price(self, obj: Item) -> object:
        return obj.total_price


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "creation_date", "checked_out", "item_count")
    list_filter = ("checked_out",)
    # ``=id`` is an exact-match lookup — integer PKs don't work with the
    # default ``icontains`` prefix. Lets admins paste a cart id into
    # the changelist search box and land on just that cart.
    search_fields = ("=id",)
    inlines = [ItemInline]

    @admin.display(description="Items")
    def item_count(self, obj: Cart) -> int:
        return obj.items.count()
