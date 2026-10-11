"""Bounded task/event windows with continuous Native, NoC, SRAM and LRU state.

Only drained graphs and observational counters are retired. Array row state,
refresh phase, physical clocks, DMA availability, router arbitration and credits
are never reset. Each archived window has an independently auditable carry pair.
"""
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import gzip,json,time
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha


def ownership(e,*,initial=False):
    c=e.weight_cache
    cache=dict(entries={t:[(k,v['size']) for k,v in entries.items()] for t,entries in c.entries.items()},
        ever_seen=sorted(c.ever_seen),used=dict(c.used),lookup_free=dict(c.lookup_free)) if c else None
    if initial and cache is not None:
        cache=dict(entries={t:[] for t in c.entries},ever_seen=[],used={},lookup_free={})
    return dict(sram={} if initial else dict(e.sram),weight_cache=cache,
        metadata_owned=not initial,fetch_metadata_bytes=e.fetch_metadata_bytes,
        context_metadata_bytes=e.context_metadata_bytes,cache_reserved_bytes=e.cache_reserved_bytes,
        physical_idle=True,clock_ps=e.now)


class RuntimeWindows:
    def __init__(self,root,producer,initial_metadata):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.producer=iter(producer);self.metadata=initial_metadata;self.rows=[];self.begin=0;self.wall=time.monotonic()

    def start(self,e):
        self.carry=ownership(e,initial=True)
        self.backend_base=(e.native.backend.accepted,e.native.backend.completed)

    def next_window(self,now):
        following=next(self.producer,None)
        if following is None:return None
        graph,kernels,self.metadata=following;self.begin=now
        return graph,kernels

    def checkpoint(self,e,makespan,quantum,advance):
        if any(e.fetch_live.values()) or e.requests or e.engine or not e.network.drained() or e.native.record()['pending']:
            raise RuntimeError('Only a fully drained physical boundary may retire a runtime window')
        native=e.native.record();native['accepted_atoms']-=self.backend_base[0];native['completed_atoms']-=self.backend_base[1]
        cache=e.weight_cache.record() if e.weight_cache else None
        out=ownership(e);tasks={k:{v:s[v] for v in ('start_ps','finish_ps','read_bytes')} for k,s in e.state.items()}
        r=dict(schema='w2w.system-execution.v3',scope='physical_real_moe_window',makespan_ps=makespan,drained_ps=e.now,
            quantum_ps=quantum,time_advance=advance,spec=asdict(e.spec),graph=asdict(e.graph),tasks=tasks,
            sram_peak_bytes=dict(e.sram_peak),compute_busy_ps=dict(e.busy_ps),engine_context_ps=dict(e.engine_context_ps),
            operand_readiness=dict(policy=e.operand_readiness,peak_metadata_bytes=dict(e.operand_metadata_peak),metadata_live_bytes=sum(e.operand_metadata_live.values())),
            compute_execution=dict(contexts_per_cluster=e.compute_contexts,context_peak=dict(e.context_peak)),
            activation_sram_read_bytes_per_cycle=e.activation_sram_read_bytes_per_cycle,
            sram_read_bytes=dict(e.sram_read_bytes),sram_read_busy_cycles=dict(e.sram_read_cycles),
            outstanding_peak=dict(e.outstanding_peak),mc_peak=dict(e.mc_peak),mc_pool_peak=dict(e.mc_pool_peak),
            network=e.network.record(),native=native,physical=e.builder.physical_record(),events=sorted(e.events,key=lambda x:x['time_ps']),
            fetch_execution=dict(contexts_per_cluster=e.fetch_contexts,peak_contexts=dict(e.fetch_peak),
                live_contexts=sum(map(len,e.fetch_live.values())),metadata_bytes_per_cluster=e.fetch_metadata_bytes,read_issue_policy=e.read_issue_policy),
            npu_execution=e.npu_model.record(),runtime_carry_in=self.carry,runtime_carry_out=out,
            runtime_window_begin_ps=self.begin,runtime_metadata=self.metadata)
        # These counters affect ordering/IDs, so keep them monotonic internally.
        r['network']['accepted_packets']-=getattr(self,'network_accepted_base',0)
        r['network']['delivered_packets']-=getattr(self,'network_delivered_base',0)
        if cache:r['weight_cache']=cache
        from w2w.validation.vertical_access import audit_vertical_result
        from w2w.validation.request_control import audit_request_control
        from w2w.validation.npu_resources import audit_npu_result
        a=audit_vertical_result(r);b=audit_request_control(r);n=audit_npu_result(r)
        expected=sum(v['M']*v['N']*v['K'] for v in self.metadata['npu_kernels'].values())
        if n['macs']!=expected:raise ValueError('Runtime window mathematical work changed')
        path=self.root/f'window-{len(self.rows):04d}.json.gz'
        with gzip.open(path,'wt',compresslevel=6) as f:json.dump(r,f)
        row=dict(index=len(self.rows),file=path.name,sha256=file_sha(path),
            begin_ps=self.begin,makespan_ps=makespan,drained_ps=e.now,tasks=len(e.tasks),
            carry_in_sha256=digest(self.carry),carry_out_sha256=digest(out),
            native_bytes=a['native_bytes'],cache_stats=cache['stats'] if cache else {},
            metadata=self.metadata,audit=a,control_audit=b,npu_audit=n,
            wall_seconds=time.monotonic()-self.wall)
        self.rows.append(row);self.carry=out
        write_json(self.root/'progress.json',dict(completed_windows=len(self.rows),latest=row))
        print(json.dumps(dict(window=row['index'],complete=True,time_ps=makespan,native_bytes=row['native_bytes'],wall_seconds=row['wall_seconds'])),flush=True)
        # Final cleanup is a distinct ledger after the last archived carry.
        e.events.clear()

    def reset_observations(self,e):
        self.backend_base=(e.native.backend.accepted,e.native.backend.completed)
        self.network_accepted_base=e.network.accepted;self.network_delivered_base=e.network.delivered
        for key in ('busy_ps','engine_context_ps','context_peak','outstanding_peak','mc_peak','mc_pool_peak',
                    'operand_metadata_peak','prefix_blocked','sram_read_bytes','sram_read_cycles'):
            getattr(e,key).clear()
        e.sram_peak=Counter(e.sram);e.fetch_peak.clear()
        if e.weight_cache:
            c=e.weight_cache;c.stats.clear();c.by_tile.clear();c.peak=Counter(c.used)
        n=e.native
        for key in ('reservation_peak','pool_peak','aggregate_bytes','aggregate_busy_cycles','aggregate_peak',
                    'channel_atoms','command_peak','domain_descriptor_peak','command_bytes','ack_peak','ack_bytes'):
            getattr(n,key).clear()
        for key in ('accepted','completed','reservation_stalls','queue_stalls','collection_atom_ps','cdc_atom_ps','gateway_atom_ps','command_stalls'):
            setattr(n,key,0)
        n.native_first_ps=n.native_last_ps=None;n.gateway_trace.clear()
        net=e.network
        for key in ('link_flits','wire_bytes','accepted_bytes','delivered_bytes','source_peak','rx_peak',
                    'injection_flits_by_source','admission_rejections','arbiter_peak'):
            getattr(net,key).clear()
        net.rejections=0;net.cell_tag_peak=0;net.link_slots.clear();net.native_ids.clear()
        for key in ('bytes','cycles','cycles_by_class','wait_ps'):getattr(net.write_port,key).clear()
        # Runtime source retires no future route or pre-instantiated Native atom.
        # Preserve the exact ownership/LRU/lookup phase in the carry chain.

    def summary(self):
        return dict(schema='w2w.runtime-window-chain.v1',windows=self.rows,completed_windows=len(self.rows),
            peak_instantiated_tasks=max(r['tasks'] for r in self.rows),
            total_completed_tasks=sum(r['tasks'] for r in self.rows),native_bytes=sum(r['native_bytes'] for r in self.rows),
            contract='Same continuous Native controllers/rows/refresh and BookSim routers/credits; '
                'same finite cache entries/LRU/ever-seen and metadata ownership. Retire only drained task/events and observational counters. '
                'Each independent two-layer window is archived before the next route DAG is generated.')
