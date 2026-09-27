# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Finish the account.edi upgrade after the new code and XML are loaded."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.l10n_pa_edi.hooks import (
        _backfill_hka_edi_documents,
        _drop_legacy_dgi_auto_send_column,
        _enable_hka_edi_on_dgi_journals,
    )

    _enable_hka_edi_on_dgi_journals(env)
    _backfill_hka_edi_documents(env)
    _drop_legacy_dgi_auto_send_column(cr)
