"""Independent fixed-byte batch resource checks."""
import numpy as np
from w2w.synthesis.cycle_configurations import primal_audit

def batch_resource_check(p,a,r,activity):
    """Build resource loads from frozen A, independent of cycle predictions."""
    primal_audit(p,a,np.ones(36),range(36))
    loads=[a[:,m].copy() for m in range(36)];caps=[1.]*36;ports={}
    for e in p.edges:
        c,m=e['c'],e['m'];v=np.zeros(36);v[c]=a[c,m]
        loads.append(v);caps.append(p.edge_bandwidth(e))
        for key,q in [(('c',c,e['cp']),4/len(p.compute[c].vertical_connectors)),(('m',m,e['mp']),4/len(p.memory[m].vertical_connectors))]:
            if key not in ports:ports[key]=(np.zeros(36),q)
            ports[key][0][c]+=a[c,m]
    for v,q in ports.values():loads.append(v);caps.append(q)
    matrix=np.array(loads);capacity=np.array(caps)
    residual=max(0.,float(np.max(r@matrix.T-capacity)),float(np.max(activity-r)),float(np.max(r-4)),float(np.max(np.abs(r[~activity]))))
    assert residual<1e-8
    h=activity.astype(float);x=r-h
    residual_form=float(np.max(x@matrix.T-(capacity-h@matrix.T)))
    assert residual_form<1e-8
    return residual
