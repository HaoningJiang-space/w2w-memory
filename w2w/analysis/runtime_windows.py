"""Read-only independent carry-chain, window work and final SRAM cleanup audit."""
import gzip,json
from collections import Counter
from pathlib import Path
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.workloads.moe_trace import file_sha
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.npu_resources import audit_npu_result
from w2w.common.event_archive import read_execution,canonical_sha


def audit_window_chain(summary,root,*,visit=None):
    if summary['schema']!='w2w.runtime-window-summary.v1':raise ValueError('Bounded summary required')
    chain=summary['runtime_windows'];rows=chain['windows'];previous=None;end=0;native=0;tasks=0;macs=0;cache=Counter()
    if not rows or len(rows)!=chain['completed_windows']:raise ValueError('Missing runtime windows')
    for index,row in enumerate(rows):
        path=Path(root)/row['file']
        if row['index']!=index or file_sha(path)!=row['sha256']:raise ValueError('Window identity/raw hash changed')
        r=read_execution(path)
        if row.get('decoded_sha256') and canonical_sha(r)!=row['decoded_sha256']:raise ValueError('Complete decoded event identity changed')
        incoming,outgoing=r['runtime_carry_in'],r['runtime_carry_out']
        if digest(incoming)!=row['carry_in_sha256'] or digest(outgoing)!=row['carry_out_sha256']:
            raise ValueError('SRAM/cache/clock carry hash changed')
        if previous is not None and incoming!=previous:raise ValueError('Continuous state reset or residency changed between windows')
        if index==0 and (incoming['sram'] or incoming['metadata_owned']):raise ValueError('Undeclared initial SRAM ownership')
        if r['runtime_window_begin_ps']!=end or row['begin_ps']!=end:raise ValueError('Window clock reset')
        if r['drained_ps']<r['makespan_ps'] or r['makespan_ps']<=end:raise ValueError('Nonmonotonic physical progress')
        if any(t['finish_ps'] is None or t['start_ps']<end for t in r['tasks'].values()):raise ValueError('Tasks escaped current causal window')
        a=audit_vertical_result(r);audit_request_control(r);n=audit_npu_result(r)
        if a!=row['audit'] or n!=row['npu_audit']:raise ValueError('Independent archived audit mismatch')
        native+=a['native_bytes'];tasks+=len(r['tasks']);macs+=n['macs'];cache.update(r.get('weight_cache',{}).get('stats',{}))
        if visit:visit(r,row)
        previous=outgoing;end=r['drained_ps']
    if summary['drained_ps']!=end or chain['native_bytes']!=native or chain['total_completed_tasks']!=tasks:
        raise ValueError('Summary changed physical work/time')
    sram=Counter(previous['sram'])
    expected={kind for kind,amount in (('compute-context-state',previous['context_metadata_bytes']),
        ('fetch-context-state',previous['fetch_metadata_bytes']),('weight-cache-partition',previous['cache_reserved_bytes'])) if amount}
    if previous.get('persistent_sram'):expected.add('kv-residency')
    seen=set()
    for e in summary['cleanup_events']:
        if e['kind']!='sram_change' or e['task'] not in expected or e['time_ps']!=end or e['bytes']>=0:
            raise ValueError('Unexplained work or allocation in final cleanup')
        key=(e['tile'],e['task'])
        if key in seen:raise ValueError('Repeated state release')
        seen.add(key);sram[e['tile']]+=e['bytes']
        if sram[e['tile']]<0:raise ValueError('Unowned final SRAM release')
    if any(sram.values()):raise ValueError('Runtime finished with live SRAM ownership')
    return dict(passed=True,windows=len(rows),tasks=tasks,native_bytes=native,macs=macs,cache_stats=dict(cache),
        makespan_ps=summary['makespan_ps'],drained_ps=end,scope='Each raw window re-audited; continuous cache/LRU/clock ownership and final metadata release closed.')
