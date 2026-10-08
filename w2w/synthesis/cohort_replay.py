"""Reconstruct frozen hardware; no mapping search or experiment execution."""
from dataclasses import replace
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.synthesis.provisioning_target import target_design


def designs():
    catalog = candidate_designs()[0]
    result = {key: catalog[key] for key in ('home', 'k2', 'wide')}
    result['c'] = target_design(192)[0]
    c = result['c']
    result['c_dup'] = replace(c, name=c.name+'_duplicated', shared_directions=(),
        endpoint=replace(c.endpoint, shared_fifo_ports=(), shared_serializer=False))
    return result
