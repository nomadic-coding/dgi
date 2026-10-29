# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Key existing HKA logs so detached (FK-less) logging can link them."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.l10n_pa_edi.hooks import _backfill_hka_log_document_keys

    _backfill_hka_log_document_keys(env)
