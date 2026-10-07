"""Frozen bank-level demand and byte-weight scenarios."""
from dataclasses import dataclass
import numpy as np
from w2w.constants import PAGES

@dataclass
class Scenario:
    pattern: str
    fraction: float
    seed: int
    demand: np.ndarray
    weights: np.ndarray

    def serializable(self):
        return dict(pattern=self.pattern, fraction=self.fraction, seed=self.seed,
                    demand_tb_s=self.demand.tolist(), page_weights=self.weights.tolist())



def scenarios(fabric, seeds, fractions=(.25,.5,.75,1.), patterns=('uniform','hotspot','clustered','correlated')):
    coordinates=np.array([(r.x,r.y) for r in fabric.compute])
    distance=np.sqrt(((coordinates[:,None]-coordinates[None,:])**2).sum(axis=2))
    kernel=np.exp(-distance**2/(2*45**2))
    n=len(coordinates); output=[]
    for pattern_id,pattern in enumerate(patterns):
        for fraction in fractions:
            for seed in seeds:
                rng=np.random.default_rng(np.random.SeedSequence([seed,pattern_id,round(100*fraction)]))
                count=max(1,round(n*fraction))
                if pattern in ('uniform','hotspot'):
                    active=rng.choice(n,count,replace=False)
                elif pattern=='clustered':
                    center=int(rng.integers(n));active=np.argsort(distance[center]+rng.uniform(0,.01,n))[:count]
                elif pattern=='correlated':
                    active=np.argsort(kernel@rng.normal(size=n))[-count:]
                else: raise ValueError('Unknown demand pattern')
                demand=np.zeros(n);demand[active]=4.
                weights=np.full(PAGES,1/PAGES)
                if pattern=='hotspot':
                    weights[:16]=.8/16;weights[16:]=.2/(PAGES-16)
                output.append(Scenario(pattern,fraction,seed,demand,weights))
    return output
