"""One staged hardware-cost ledger for immutable designs."""
from math import ceil, log2


class CostModel:
    @staticmethod
    def evaluate(candidate, serializer_location=None):
        """Separate long access wires, endpoint buffers, pipeline and control proxy."""
        x = candidate.exposure
        g = candidate.geometry
        s = candidate.endpoint
        banks = len(x.mask)
        location = serializer_location or s.serializer_location
        if location not in ('bank', 'port'):
            raise ValueError('Unknown serializer placement')
        group = s.shared_fifo_ports
        if group and location != 'bank':
            raise ValueError('Shared FIFO is bank-local; port-side pooling needs an explicit physical design')
        xy = g.bank_xy
        lengths = []
        lanes = storage = pipeline = 0
        bit_mm = 0.
        for b, ports in enumerate(x.mask):
            if s.mode == 'direct':
                storage += s.word_bits
            for p in ports:
                connector = g.port_xy[p]
                length = float(abs(xy[b][0] - connector[0]) + abs(xy[b][1] - connector[1]))
                lengths.append(length)
                width = s.widths[p] if location == 'bank' else s.word_bits
                bit_mm += width * length
                pipeline += ceil(length / x.pipeline_spacing_mm) * width
                lanes += s.widths[p]
                if s.mode == 'buffered':
                    if p not in group or p == group[0]:
                        storage += s.depths[p] * s.word_bits
        # Explicit per-bank fixed sequence ROM + cursor encoding, not a cell-area claim.
        period = candidate.home_fraction.denominator
        destination_bits = ceil(log2(len(x.port_bits)))
        sequence_storage = banks * (period * destination_bits + ceil(log2(period)))
        return dict(bank_port_connections=len(lengths), export_lane_bits=lanes,
                    endpoint_storage_bits=storage, pipeline_register_bits=pipeline,
                    wire_mm=sum(lengths), access_wire_bit_mm=bit_mm,
                    configured_hb_signal_bits=sum(x.port_bits),
                    configured_hb_tb_s=sum(x.port_bits) * x.clock_ghz / 8000,
                    port_bits=list(x.port_bits),
                    fixed_sequence_control_bits=sequence_storage,
                    selector_input_bits=sum(len(ps) * s.word_bits for ps in x.mask),
                    # Whole-word 1:N selector before retained per-direction serializers.
                    static_direction_selector_count=banks if group else 0,
                    static_direction_selector_input_bits=banks * s.word_bits if group else 0,
                    static_direction_selector_output_bits=banks * s.word_bits * len(group),
                    static_direction_config_bits=ceil(log2(len(group))) if group else 0,
                    static_direction_selector_wire_bit_mm=None if group else 0.,
                    serializer_instances=sum(0 < s.widths[p] < s.word_bits for ps in x.mask for p in ps),
                    serializer_location=location, local_selector_wire_bit_mm=None,
                    pipeline_spacing_mm=x.pipeline_spacing_mm,
                    scope='Per-memory repeated-template proxies; local selector wire unknown; no PPA; old buffer proxy excluded')
