"""A fixed 256-to-128 B C-C intervention; graph and all other services stay frozen."""
from copy import deepcopy
from w2w.common.fingerprints import digest_system_v2 as digest


def cc_width_contract(reference, candidate):
    for name in ('graph','metadata','architecture','streaming','services'):
        if reference[name]!=candidate[name]:raise ValueError('C-C control changed '+name)
    a,b=reference['spec'],candidate['spec']
    if (a['flit_bytes'],b['flit_bytes'])!=(256,128):
        raise ValueError('This control requires the fixed 256-to-128 B intervention')
    expected=deepcopy(a)
    expected.update(flit_bytes=128,input_buffer_flits=32,injection_flits=512)
    for link in expected['links']:
        if link['kind']!='HB':link['width_bits']=1024
    if b!=expected or a['input_buffer_flits']!=16 or a['injection_flits']!=256:
        raise ValueError('C-C control changed clocks, latency, buffers in bytes or another resource')
    geometry=deepcopy(reference['physical']);actual=deepcopy(candidate['physical'])
    cc={l['resource_id'] for l in a['links'] if l['kind']!='HB'}
    for path in geometry['paths']:
        if path['resource_id'] in cc:
            path['data_bits']=1024
            path['data_wire_bit_mm']/=2;path['link_register_bits']//=2
        path['credit_window_flits']=32
        path['propagation_only_flits_per_cycle_upper']=min(1,32/(2*path['data_cycles']))
    geometry.pop('machine_sha256');actual.pop('machine_sha256')
    if geometry!=actual:raise ValueError('C-C control changed spatial geometry or another physical assumption')
    return dict(passed=True,graph_sha256=digest(reference['graph']),
        metadata_sha256=digest(reference['metadata']),services_sha256=digest(reference['services']),
        reference_input_sha256=digest(reference),candidate_input_sha256=digest(candidate),
        changed='C-C data width and corresponding cell counts; all byte capacities and other services fixed',
        input_buffer_bytes=4096,source_ni_bytes=65536,local_dma_payload_beat_bytes=256,
        receive_write_bytes_per_cycle=256,reference_cell_bytes=256,candidate_cell_bytes=128,
        sideband_bits_per_cell=64,scope='fixed four-token row-batched candidate; not an area/PPA claim')
