"""Seeded reticle activity distributions shared by synthesis and audits."""
import numpy as np

KINDS=('random25','random50','cluster25','correlated25')

def scenarios(seed, n=36):
    from scipy.ndimage import gaussian_filter
    rng=np.random.default_rng(seed)
    xy=np.array([(i%6,i//6) for i in range(n)])
    center=xy[rng.integers(n)];dist=((xy-center)**2).sum(axis=1)
    smooth=gaussian_filter(rng.normal(size=(6,6)),1.,mode='reflect').ravel()
    return [('random25',sorted(rng.choice(n,9,replace=False).tolist())),
            ('random50',sorted(rng.choice(n,18,replace=False).tolist())),
            ('cluster25',np.lexsort((rng.random(n),dist))[:9].tolist()),
            ('correlated25',np.argsort(-smooth)[:9].tolist())]


def activity_sets(seeds):
    out={kind:[] for kind in KINDS}
    for seed in seeds:
        for kind,active in scenarios(seed):
            row=np.zeros(36,bool);row[active]=True;out[kind].append(row)
    return {k:np.array(v) for k,v in out.items()}
