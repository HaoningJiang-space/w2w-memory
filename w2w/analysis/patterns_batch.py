"""Routing-content diagnostics with frozen ownership; no application speedup claim."""
import numpy as np


def windows(routes, order, batch_size):
    """Equal-length observed decode prefixes, fixed cohorts, never duplicate/pad."""
    if routes.dtype != np.bool_ or routes.ndim != 4:
        raise ValueError('Expected request x step x layer x expert boolean selections')
    if len(set(order)) != len(routes) or set(order) != set(range(len(routes))):
        raise ValueError('Order must contain each independent request exactly once')
    for start in range(0, len(order), batch_size):
        group = routes[order[start:start+batch_size]]
        union = np.any(group, axis=0).reshape(-1,routes.shape[-1])
        # Exact per-window token-selection reference; not presumed weight bytes.
        routed = group.sum(axis=(0,3)).reshape(-1)
        yield union, routed, len(group)


def metric_arrays(union, routed, owners, pairs, compute_count=36):
    """All memory-related times below are memory-only lower bounds, not execution."""
    mapping = np.eye(compute_count,dtype=np.int32)[owners]
    counts = union.astype(np.int32) @ mapping
    distinct = union.sum(axis=1)
    if np.any(distinct==0):raise ValueError('Empty read window')
    active = counts>0
    peak = counts.max(axis=1)
    pair_load = np.stack([(counts[:,i]+counts[:,j])/2 for i,j in pairs],axis=1)
    pair_peak = pair_load.max(axis=1)
    # Conditional directed observations: active client with idle fixed partner.
    busy_idle=sum((active[:,i] & ~active[:,j]).astype(np.int32)+
                  (active[:,j] & ~active[:,i]).astype(np.int32) for i,j in pairs)
    mismatch=sum(np.abs(counts[:,i]-counts[:,j]) for i,j in pairs)
    return counts,dict(distinct=distinct, routed=routed, active=active.sum(axis=1),
        reuse_saved=1-distinct/routed, imbalance=peak/(distinct/compute_count),
        home_peak=peak, pair_peak=pair_peak,
        idle_partner_events=busy_idle, paired_imbalance=mismatch/distinct,
        bank_only_ratio=peak/pair_peak)


def summarize(routes, order, batch_size, owners, pairs):
    if sorted(x for pair in pairs for x in pair)!=list(range(36)):
        raise ValueError('Pairs must be a disjoint cover of the frozen 36-compute design')
    parts={};cohort_rows=[];streak_lengths=[];sum_d=np.zeros(36);sum_sq=np.zeros(36);cross=np.zeros((36,36));total=0
    for union,routed,actual_size in windows(routes,order,batch_size):
        counts,values=metric_arrays(union,routed,owners,pairs)
        # Idle-partner runs stay within a cohort and one selected layer.
        peer=np.empty(36,dtype=int)
        for i,j in pairs:peer[i]=j;peer[j]=i
        active=counts.reshape(routes.shape[1],routes.shape[2],36)>0
        events=active & ~active[:,:,peer]
        flat=np.pad(events.transpose(1,2,0),((0,0),(0,0),(1,1))).reshape(-1).astype(np.int8)
        changes=np.diff(flat)
        starts=np.flatnonzero(changes==1);ends=np.flatnonzero(changes==-1)
        streak_lengths.extend((ends-starts).tolist())
        d=counts.astype(float)
        sum_d+=d.sum(axis=0);sum_sq+=(d*d).sum(axis=0);cross+=d.T@d;total+=len(d)
        for key,value in values.items():parts.setdefault(key,[]).append(value)
        cohort_rows.append(dict(request_count=actual_size,windows=len(d),
            reuse_saved=float(1-values['distinct'].sum()/values['routed'].sum()),
            active_compute_mean=float(values['active'].mean())))
    a={key:np.concatenate(value) for key,value in parts.items()}
    mean=sum_d/total;variance=sum_sq/total-mean**2
    denom=np.sqrt(np.maximum(variance,0)[:,None]*np.maximum(variance,0)[None,:])
    corr=np.divide(cross/total-np.outer(mean,mean),denom,out=np.full_like(denom,np.nan),where=denom>1e-12)
    pc=[float(corr[i,j]) for i,j in pairs if np.isfinite(corr[i,j])]
    result=dict(windows=total,cohorts=cohort_rows,
        distinct_experts_mean=float(a['distinct'].mean()),
        weight_read_reuse_saved=float(1-a['distinct'].sum()/a['routed'].sum()),
        token_times_weight_to_union_ratio=float(a['routed'].sum()/a['distinct'].sum()),
        active_compute_mean=float(a['active'].mean()),
        active_compute_p95=float(np.quantile(a['active'],.95)),
        peak_to_mean_demand=float(a['imbalance'].mean()),
        active_client_idle_partner_fraction=float(a['idle_partner_events'].sum()/a['active'].sum()),
        occupancy_conditioned_idle_partner_null=float((a['active']*(36-a['active'])/35).sum()/a['active'].sum()),
        idle_partner_streak_mean_decode_steps=float(np.mean(streak_lengths)) if streak_lengths else 0.,
        idle_partner_streak_p95_decode_steps=float(np.quantile(streak_lengths,.95)) if streak_lengths else 0.,
        pair_absolute_load_mismatch_fraction=float(a['paired_imbalance'].mean()),
        paired_demand_correlation_mean=float(np.mean(pc)) if pc else None,
        paired_demand_correlation_defined=len(pc),
        paired_negative_correlation_count=sum(v<0 for v in pc),
        bank_only_sequential_bound_ratio=float(a['home_peak'].sum()/a['pair_peak'].sum()),
        bank_only_window_ratio_mean=float(a['bank_only_ratio'].mean()),
        window_bank_only_ratio_p5=float(np.quantile(a['bank_only_ratio'],.05)))
    return result
