# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.l10n_pa_edi.hooks import _normalize_dgi_status_case

    _normalize_dgi_status_case(env)
