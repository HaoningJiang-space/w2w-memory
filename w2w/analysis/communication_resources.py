"""Communication resource proxies, separated by stage and storage unit; no PPA."""
from math import ceil,log2
from collections import Counter
from w2w.machine.rwdl_layout import grid_collection_reference


def receive_service_work(record):
    """Frozen payload-beat local DMA and per-cell remote writes, independent of timing."""
    spec=record['spec'];tasks={t['id']:t for t in record['graph']['tasks']}
    objects={o['id']:o for o in record['graph']['objects']}
    homes={m['id']:m['home_tile'] for m in spec['memories']}
    local,remote,byte_counts=Counter(),Counter(),Counter()
    def transfer(src,dst,kind,size):
        for offset in range(0,size,spec['packet_payload_bytes']):
            part=min(spec['packet_payload_bytes'],size-offset);key=dst+'/'+kind
            byte_counts[key]+=part
            if src==dst:local[key]+=ceil(part/spec['rx_write_bytes_per_cycle'])
            else:remote[key]+=ceil((part+spec['header_bytes'])/spec['flit_bytes'])
    for t in tasks.values():
        for r in t['reads']:transfer(homes[objects[r['object_id']]['memory']],t['tile'],'response',r['size_bytes'])
    for e in record['graph']['data']:
        transfer(tasks[e['producer']]['tile'],tasks[e['consumer']]['tile'],'activation',e['size_bytes'])
    return dict(local_cycles_by_class=dict(local),remote_cycles_by_class=dict(remote),
        total_cycles_by_class=dict(local+remote),bytes_by_class=dict(byte_counts),
        policy='local 256 B payload beats; remote each cell consumes one write job, short writes rounded independently')


def communication_resources(record):
    spec=record['spec'];physical=record['physical']
    ids={l['resource_id'] for l in spec['links'] if l['kind']!='HB'}
    paths=[p for p in physical['paths'] if p['resource_id'] in ids]
    n=len(spec['tiles']);m=len(spec['memories']);sideband=64
    width=spec['flit_bytes'];slots=spec['input_buffer_flits'];ni=spec['injection_flits']
    interface=record['services']['memory']['interface']
    controller=record['services']['memory']['controller']
    arrays=interface['arrays'];lanes=arrays*interface['bits_per_array']
    internal=grid_collection_reference()
    return dict(schema='w2w.communication-resources.v1',calibrated=False,area_um2=None,energy_j=None,
        rw_dl_hb=dict(shared_data_lanes_per_memory=lanes,total_shared_data_lanes=m*lanes,
            period_ps=interface['period_ps'],duplicate_rw_dl_hb_charge=False,command_address_lanes=None,
            interface_area_um2=None),
        internal_collection=dict(reference=internal['scope'],included_in_runtime=False,
            data_wire_bit_mm=internal['data_wire_bit_mm_per_memory']*m,
            data_pipeline_bits=internal['data_pipeline_bits_per_memory_reference']*m,
            controller_area_um2=None,command_control_cost=None),
        cc=dict(directed_links=len(paths),data_bits=width*8,sideband_bits=sideband,
            data_wire_bit_mm=sum(p['data_wire_bit_mm'] for p in paths),
            data_pipeline_bits=sum(p['link_register_bits'] for p in paths),
            sideband_wire_bit_mm=sum(p['length_um']*sideband/1000 for p in paths),
            sideband_pipeline_bits=sum(p['data_cycles']*sideband for p in paths),
            credit_wire_bit_mm=sum(p['credit_wire_bit_mm'] for p in paths),
            credit_pipeline_bits=sum(p['credit_register_bits'] for p in paths)),
        buffers_control=dict(input_data_bytes_per_port=slots*width,input_cells_per_port=slots,
            cc_input_data_bytes=len(paths)*slots*width,
            cc_input_sideband_bytes=len(paths)*slots*sideband//8,
            router_local_input_ports=n,router_local_input_data_bytes=n*slots*width,
            router_local_input_sideband_bytes=n*slots*sideband//8,
            native_ejection_data_bytes=n*slots*width,
            native_ejection_sideband_bytes=n*slots*sideband//8,
            source_ni_data_bytes=n*ni*width,source_ni_cells=n*ni,
            source_ni_sideband_storage_reference_bytes=n*ni*sideband//8,
            destination_message_reservation_slots=n*3*spec['ejection_packets'],
            destination_message_capacity_bytes=n*3*spec['ejection_packets']*(spec['packet_payload_bytes']+spec['header_bytes']),
            message_tag_pool_slots=65536,message_tag_bits=16,
            native_command_entries_per_memory=arrays*controller['read_entries'],
            native_command_entry_bare_min_bits_per_memory=arrays*controller['read_entries']*24,
            native_row_hint_bits_per_memory=arrays*15,
            native_row_comparators_per_memory=arrays*controller['descriptor_window'],
            native_cdc_reservation_bytes_per_memory=arrays*8*16,
            shared_mc_return_bytes_per_memory=max(mm['transaction_slots'] for mm in spec['memories'])*spec['memory_request_bytes'],
            credit_counter_min_bits_per_input=ceil(log2(slots+1)),
            counter_scope='one occupancy/credit count per input, not a complete controller cost',
            cell_sideband_storage_scope='64 bits/cell retained in router/endpoint storage; source NI is a storage reference, descriptor packing not implemented',
            allocator_arbitration_area_um2=None,extra_slot_control_bits=None),
        fixed_services=dict(local_dma_payload_beat_bytes=spec['rx_write_bytes_per_cycle'],
            receive_write_bytes_per_cycle=spec['rx_write_bytes_per_cycle'],
            source_sram_read_bytes_per_cycle=record['services']['compute']['external_read_bytes_per_cycle'],
            compute_weight_read_bytes_per_cycle=record['services']['compute']['weight_read_bytes_per_cycle'],
            memory_service=record['services']['memory']),
        exclusions='Uncalibrated internal layout, controller/clock/address logic and SRAM macro costs; proxies cannot be summed as area or energy')
