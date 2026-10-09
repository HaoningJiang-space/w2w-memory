"""Product-inspired distributed compute, with explicit aggregate-to-fine ratios.

48 KiB SRAM/core, four FP16 FMAC datapaths, 16-data/16-control-bit wavelets and
one-cycle fine neighbor links are public architectural anchors. Clock, aggregate
router behavior and FP8 conversion throughput remain research assumptions.
"""
from math import ceil
from ..compute_fabric import ReticleRegion, ComputeCluster, Router, ComputeProfile
from ..physical_graph import WireSegment, FabricChannel


def distributed_compute(rows=2, columns=2, *, profile=ComputeProfile()):
    if not 1 <= rows <= 6 or not 1 <= columns <= 6: raise ValueError('Supported physical field array is 1..6')
    regions, clusters, routers, channels = [], [], [], []
    width, height, gap = 26000, 33000, 100
    extent = (columns*width+(columns-1)*gap, rows*height+(rows-1)*gap)
    grid = {}
    for ry in range(rows):
        for rx in range(columns):
            region = ReticleRegion(f'cr{ry*columns+rx}',
                (rx*(width+gap)-extent[0]//2, ry*(height+gap)-extent[1]//2), (width,height), 'compute')
            regions.append(region)
            for y in range(2):
                for x in range(2):
                    gx, gy = rx*2+x, ry*2+y
                    n = gy*(columns*2)+gx
                    pos = (region.origin_um[0]+(2*x+1)*width//4,
                           region.origin_um[1]+(2*y+1)*height//4)
                    router = Router(f'r{n}', region.id, pos)
                    cluster = ComputeCluster(f'c{n}', region.id, pos, router.id, profile)
                    routers.append(router); clusters.append(cluster); grid[gx,gy] = router
    by_region = {r.id:r for r in regions}
    for (x,y), src in sorted(grid.items()):
        for target in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if target not in grid: continue
            dst = grid[target]; a,b = src.position_um,dst.position_um
            if src.reticle_id == dst.reticle_id:
                segments = (WireSegment('intra_reticle',a,b,64),)
                hops = 64
            else:
                # The scribe-line crossing is 100 um. Region-center distance is
                # paid by the surrounding intra-region fine-router pipelines.
                reg = by_region[src.reticle_id]
                if x != target[0]:
                    direction = 1 if target[0]>x else -1
                    edge = reg.origin_um[0]+(reg.size_um[0] if direction>0 else 0)
                    p=(edge,a[1]); q=(edge+direction*gap,a[1])
                else:
                    direction = 1 if target[1]>y else -1
                    edge = reg.origin_um[1]+(reg.size_um[1] if direction>0 else 0)
                    p=(a[0],edge); q=(a[0],edge+direction*gap)
                segments = (WireSegment('intra_reticle',a,p,32),
                    WireSegment('boundary_stitch',p,q,1),WireSegment('intra_reticle',q,b,32))
                hops = 65
            channels.append(FabricChannel(f'{src.id}>{dst.id}', src.id,dst.id,segments,
                period_ps=profile.period_ps,channel_cycles=hops-3,fine_hops=hops))
    return tuple(regions),tuple(clusters),tuple(routers),tuple(channels)
