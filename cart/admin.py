from django.contrib import admin
from .models import Cart, Item


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0
    readonly_fields = ("content_type", "object_id", "unit_price", "quantity")

    def total_price(self, obj):
        return obj.total_price
    total_price.short_description = "Total"


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "creation_date", "checked_out", "item_count")
    list_filter = ("checked_out",)
    # ``=id`` is an exact-match lookup — integer PKs don't work with the
    # default ``icontains`` prefix. Lets admins paste a cart id into
    # the changelist search box and land on just that cart.
    search_fields = ("=id",)
    inlines = [ItemInline]

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = "Items"
