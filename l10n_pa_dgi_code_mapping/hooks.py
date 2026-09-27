# -*- coding: utf-8 -*-


def _auto_map_standard_records(env):
    """Link PA / PAB / USD / Units to DGI catalog rows when still empty."""

    def _map_record(record, xmlid):
        if not record or record.dgi_code_id:
            return
        mapping = env.ref(xmlid, raise_if_not_found=False)
        if mapping:
            record.sudo().dgi_code_id = mapping

    _map_record(env.ref("base.pa", raise_if_not_found=False), "dgi_mapping_917")
    _map_record(env.ref("base.USD", raise_if_not_found=False), "dgi_mapping_728")
    _map_record(env.ref("base.PAB", raise_if_not_found=False), "dgi_mapping_690")
    _map_record(env.ref("uom.product_uom_unit", raise_if_not_found=False), "dgi_mapping_504")


def post_init_hook(env):
    _auto_map_standard_records(env)
