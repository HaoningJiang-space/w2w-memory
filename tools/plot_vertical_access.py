#!/usr/bin/env python3
"""Standalone scientific figure from completed, independently audited results."""
import argparse,json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--analysis',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
args=p.parse_args()
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

report=json.loads(args.analysis.read_text())
if not report['passed'] or not report['comparison']['budget']['passed']:
    raise ValueError('Audited matched evidence required')
names=('central','distributed');labels=('Central','Distributed')
values=[report['cases'][n] for n in names]
fig,axes=plt.subplots(1,2,figsize=(8,3.3),layout='constrained')
bars=axes[0].bar(labels,[r['makespan_us'] for r in values],color=['#657385','#167d96'],width=.55)
for bar,row in zip(bars,values):
    axes[0].text(bar.get_x()+bar.get_width()/2,bar.get_height()+16,f"{row['makespan_us']:.3f}",ha='center',fontsize=10)
axes[0].set_ylabel('Layer completion (µs)');axes[0].set_ylim(0,1000)
axes[0].set_title('Same DRAM, compute, SRAM and HB data budget',fontsize=10)
bottom=[0,0]
components=(('Compute fabric','#bdc6d1',lambda r:r['resources']['fabric']['data_wire_bit_um']),
            ('Raw collection','#167d96',lambda r:r['resources']['collection']['wire_bit_um']),
            ('Gateway access','#df9b48',lambda r:r['resources']['gateways']['router_access_wire_bit_um']))
for name,color,get in components:
    y=[get(r)/1000000 for r in values]
    axes[1].bar(labels,y,bottom=bottom,label=name,color=color,width=.55)
    bottom=[a+b for a,b in zip(bottom,y)]
axes[1].set_ylabel('Data wire proxy (kbit·mm)')
axes[1].set_title('Resource proxy; uncalibrated PPA',fontsize=10)
axes[1].legend(frameon=False,fontsize=8,loc='upper right')
for ax in axes:
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
fig.suptitle('First Architecture V3 vertical-access comparison',fontsize=12)
fig.savefig(args.output)
