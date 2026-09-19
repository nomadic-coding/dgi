# -*- coding: utf-8 -*-

"""Prepare 18.0.1.1.0 before the new account.edi fields are loaded.

``dgi_auto_send_on_post`` is removed from the model. The column is dropped in
end-migrate after the new Python is loaded, so the old registry can still read
it during this step.
"""


def migrate(cr, version):
    # Intentionally no data rewrite. Posted invoices keep dgi_cufe / dgi_status
    # so the computed dgi_sent field stays correct after the schema update.
    return
