"""One physical resource ledger; no PPA values are inferred from these proxies."""
from dataclasses import asdict,dataclass
from math import ceil


@dataclass(frozen=True)
class ResourceBudget:
    pes: int
    macs_per_cycle: int
    sram_bytes: int
    native_domains: int
    dram_capacity_bytes: int
    hb_data_bits: int
    gateway_output_bytes_per_cycle: int
    gateway_staging_bytes: int
    gateway_descriptor_slots: int
    routers: int
    router_input_bytes: int
    router_injection_bytes: int
    fabric_data_bits: int

    @classmethod
    def from_stack(cls,stack):
        return cls(sum(c.profile.pe_count for c in stack.compute_clusters),
            sum(c.profile.macs_per_cycle for c in stack.compute_clusters),
            sum(c.profile.sram_bytes for c in stack.compute_clusters),len(stack.dram_domains),
            sum(d.capacity_bytes for d in stack.dram_domains),sum(p.data_bits for p in stack.vertical_ports),
            sum(g.data_bytes_per_cycle for g in stack.gateways),sum(g.staging_bytes for g in stack.gateways),
            sum(g.descriptor_slots for g in stack.gateways),len(stack.routers),
            sum(r.input_buffer_bytes*r.port_budget for r in stack.routers),
            sum(r.injection_buffer_bytes for r in stack.routers),sum(c.data_bits for c in stack.lateral_links))

    def validate(self,stack):
        actual=ResourceBudget.from_stack(stack)
        for key,value in asdict(actual).items():
            if value>getattr(self,key):raise ValueError(f'Physical {key} exceeds immutable machine budget; declare and charge a new budget')


def inventory(stack):
    clusters, domains = stack.compute_clusters, stack.dram_domains
    channels = stack.lateral_links
    routers={r.id:r for r in stack.routers}
    access=[dict(gateway=g.id,length_um=sum(abs(a-b) for a,b in zip(g.position_um,routers[g.router_id].position_um)),
        data_bits=g.data_bytes_per_cycle*8,pipeline_cycles=g.router_access_cycles) for g in stack.gateways]
    return dict(schema='w2w.physical-resources.v3',
        resource_budget=asdict(stack.resource_budget),
        compute=dict(clusters=len(clusters), pes=sum(c.profile.pe_count for c in clusters),
            macs_per_cycle=sum(c.profile.macs_per_cycle for c in clusters),
            vector_ops_per_cycle=sum(c.profile.vector_ops_per_cycle for c in clusters),
            sram_bytes=sum(c.profile.sram_bytes for c in clusters),
            compute_weight_read_bytes_per_cycle=sum(c.profile.weight_read_bytes_per_cycle for c in clusters)),
        native=dict(domains=len(domains), capacity_bytes=sum(d.capacity_bytes for d in domains),
            interface_peak_bytes_per_ps=sum(d.data_bits/8/d.period_ps for d in domains),
            command_entries=sum(d.command_read_entries for d in domains),
            command_metadata_bare_min_bits=sum(d.command_read_entries*((d.capacity_bytes//16-1).bit_length()
                +(d.return_atoms-1).bit_length()+1) for d in domains),
            reserved_return_bytes=sum(d.return_atoms*16 for d in domains)),
        vertical=dict(ports=len(stack.vertical_ports), data_bits=sum(p.data_bits for p in stack.vertical_ports),
            control_bits=sum(p.control_bits for p in stack.vertical_ports),
            hb_sites=sum(p.hb_sites for p in stack.vertical_ports),
            landing_footprint_um2=sum((p.landing_bounds_um[2]-p.landing_bounds_um[0])*(p.landing_bounds_um[3]-p.landing_bounds_um[1]) for p in stack.vertical_ports),
            landing_pitch_scope='declared 4 um candidate grid; geometry check, not process/PPA calibration'),
        gateways=dict(count=len(stack.gateways),
            output_bytes_per_cycle=sum(g.data_bytes_per_cycle for g in stack.gateways),
            staging_bytes=sum(g.staging_bytes for g in stack.gateways),
            descriptor_slots=sum(g.descriptor_slots for g in stack.gateways),
            control_bits=sum(g.control_bits for g in stack.gateways),
            router_access_wire_bit_um=sum(a['length_um']*a['data_bits'] for a in access),
            router_access_pipeline_bits=sum(a['pipeline_cycles']*a['data_bits'] for a in access),
            router_access_paths=access),
        external=dict(ports=len(stack.external_ports),
            bytes_per_cycle=sum(p.data_bytes_per_cycle for p in stack.external_ports),
            staging_bytes=sum(p.staging_bytes for p in stack.external_ports),
            edge_access_wire_bit_um=sum(p.data_bytes_per_cycle*8*sum(abs(a-b) for a,b in zip(p.position_um,routers[p.router_id].position_um)) for p in stack.external_ports),
            edge_access_pipeline_bits=sum(p.data_bytes_per_cycle*8*64 for p in stack.external_ports),
            scope='external DRAM, edge I/O and system cost are additional; not equal-cost vertical baseline'),
        collection=dict(paths=len(stack.collection_paths),
            timing_profiles=sorted({p.timing_profile for p in stack.collection_paths}),
            wire_bit_um=sum(p.data_bits*p.length_um for p in stack.collection_paths),
            pipeline_bits=sum(p.data_bits*p.pipeline_cycles for p in stack.collection_paths),
            delay_in_execution=True, shared_native_service=True),
        fabric=dict(routers=len(stack.routers), channels=len(channels),
            data_wire_bit_um=sum(c.data_bits*c.length_um for c in channels),
            control_wire_bit_um=sum(c.control_bits*c.length_um for c in channels),
            data_pipeline_bits=sum(c.data_bits*sum(s.pipeline_cycles for s in c.segments) for c in channels),
            control_pipeline_bits=sum(c.control_bits*sum(s.pipeline_cycles for s in c.segments) for c in channels),
            input_data_buffer_bytes=sum(r.input_buffer_bytes*r.port_budget for r in stack.routers),
            injection_buffer_bytes=sum(r.injection_buffer_bytes for r in stack.routers),
            receive_staging_bytes=len(stack.routers)*3*16*(4096+16),
            input_cell_metadata_bytes=sum((r.input_buffer_bytes//128)*r.port_budget*8 for r in stack.routers),
            injection_cell_metadata_bytes=sum((r.injection_buffer_bytes//128)*8 for r in stack.routers),
            boundary_stitch_length_um=sum(s.length_um for c in channels for s in c.segments if s.kind=='boundary_stitch'),
            aggregated_fine_links_per_channel=64, fine_data_bits_per_link=16,
            fine_control_bits_per_link=16,
            aggregation='one BookSim macro channel represents a fine-mesh cut and its ordered pipeline; not a cycle-exact Cerebras router model'),
        area_um2=None, energy_j=None,
        calibration='candidate physical layout and resource proxies; macro timing and SRAM banking are explicit assumptions')


def matched_vertical_budget(a, b):
    left, right = inventory(a), inventory(b)
    for section in ('compute', 'native', 'fabric'):
        if left[section] != right[section]: raise ValueError(f'Mismatched {section} resources')
    for key in ('data_bits',):
        if left['vertical'][key] != right['vertical'][key]: raise ValueError('HB data budget changed')
    for key in ('output_bytes_per_cycle', 'staging_bytes', 'descriptor_slots'):
        if left['gateways'][key] != right['gateways'][key]: raise ValueError(f'Gateway {key} changed')
    return dict(passed=True, conserved=['compute', 'SRAM', 'native capacity and service', 'fabric',
        'HB data lanes', 'gateway output', 'gateway staging', 'descriptor slots'],
        additional_control_bits=right['vertical']['control_bits']+right['gateways']['control_bits']
            -left['vertical']['control_bits']-left['gateways']['control_bits'],
        collection_wire_bit_um_change=right['collection']['wire_bit_um']-left['collection']['wire_bit_um'],
        metadata='ports/control and raw collection wire/pipeline costs are reported, not assumed equal')


def cell_format(node_count, flit_bytes, payload_bytes=4096, endpoint_count=None):
    fields = dict(source_router=max(1, (node_count-1).bit_length()),
        destination_router=max(1, (node_count-1).bit_length()), tag=16,
        ordinal=(ceil((payload_bytes+16)/flit_bytes)-1).bit_length(),
        valid_bytes=flit_bytes.bit_length(), traffic_class=2, first_last=2,
        local_endpoint=max(1, ((endpoint_count or node_count)-1).bit_length()))
    total = sum(fields.values())
    return dict(fields=fields, required_bits=total, sideband_bits=ceil(total/8)*8,
        contract='metadata fits declared control lanes; no free C++ object fields; tags are finite and released on commit')
