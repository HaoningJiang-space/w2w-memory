"""Declared resource presets, independent of routing and FFN compilation."""
from dataclasses import replace
from w2w.domain.system import mesh_system


def machine(*, wide=False, cc_flit_bytes=None):
    """Declared synthetic 36-reticle service machine; not a calibrated product."""
    if cc_flit_bytes is not None and (wide or type(cc_flit_bytes) is not int
                                    or cc_flit_bytes not in (128,256,512)):
        raise ValueError('Use one explicit supported C-C width or the historical wide preset')
    flit = cc_flit_bytes if cc_flit_bytes is not None else (512 if wide else 256)
    spec = mesh_system(6, 6, flit_bytes=flit, router_cycles=3,
        input_buffer_flits=4096//flit, injection_flits=65536//flit,
        ejection_packets=16, packet_payload_bytes=4096, memory_request_bytes=4096,
        read_requests_per_tile_cycle=4, outstanding_per_tile=32,
        rx_write_bytes_per_cycle=256, ideal_dram_cycles=20)
    return replace(spec,
        tiles=tuple(replace(t, sram_bytes=2*1024**2) for t in spec.tiles),
        memories=tuple(replace(m, transaction_slots=32) for m in spec.memories),
        links=tuple(replace(l, width_bits=2048) if l.kind == 'HB' else l for l in spec.links))
