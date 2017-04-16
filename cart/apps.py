# -*- coding: utf-8 -*-

from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class CartConfig(AppConfig):
    name = 'cart'
    verbose_name = _('Cart')
