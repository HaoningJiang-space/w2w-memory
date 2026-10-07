"""Show the return-path capacity explanation and all frozen-window outcomes."""
import argparse
from fractions import Fraction
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def render(source, output):
    data = json.loads(Path(source).read_text())
    plt.rcParams.update({'font.size': 9, 'svg.fonttype': 'none', 'pdf.fonttype': 42})
    fig, axes = plt.subplots(2, 2, figsize=(11.8, 8.0), layout='constrained')
    ax = axes[0, 0]
    for depth, color in ((2, '#bf573a'), (3, '#2878a5')):
        rows = [r for r in data['profiles'] if r['rx_depth']==depth]
        ax.plot([r['width_bits'] for r in rows], [float(Fraction(r['words_per_slot'])) for r in rows],
                marker='o', label=f'RX{depth}: periodic word execution', color=color)
    ax.set(xlabel='Shared width (bits)', ylabel='Delivered words / native slot',
           title='(a) A wider TX still needs enough RX reservations', xticks=[128,160,192,224,256])
    ax.legend(frameon=False, fontsize=8)
    ax = axes[0, 1]
    labels = ['b_cfg', 'c_n192', 'b_cfg_rx3', 'c_n192_rx3']
    names = ['B / RX2', 'C / RX2', 'B / RX3', 'C / RX3']
    cases = [f'h{g}_b{b}' for g in range(3) for b in (1,4,16)]
    index = {(r['case'],r['label']):r for r in data['metrics']}
    values = np.array([[index[c,k]['speedup_over_home'] for c in cases] for k in labels])
    image = ax.imshow(values, vmin=1, vmax=max(1.01, values.max()), cmap='Blues', aspect='auto')
    for i in range(len(labels)):
        for j in range(len(cases)):
            ax.text(j,i,f'{values[i,j]:.2f}',ha='center',va='center', fontsize=8,
                    color='white' if values[i,j] > 1+(values.max()-1)*.6 else '#172b3a')
    ax.set(xticks=range(len(cases)), xticklabels=[c.replace('h','').replace('_b',' / ') for c in cases],
           yticks=range(len(labels)), yticklabels=names, xlabel='Frozen group / batch size',
           title='(b) All nine read stages: speedup over trained Home')
    fig.colorbar(image, ax=ax, shrink=.7, label='Read-stage speedup')
    ax = axes[1, 0]
    rows = data['owner_controls']
    values = [r['trained_speedup_over_modulo'] for r in rows]
    ax.bar(range(len(rows)), values, color=['#2878a5' if v>=1 else '#bf573a' for v in values])
    ax.axhline(1, color='#444444', linestyle='--', linewidth=1)
    ax.set(xticks=range(len(rows)), xticklabels=[r['case'].replace('h','').replace('_b',' / ') for r in rows],
           ylabel='Modulo time / trained-mapping time', xlabel='Frozen group / batch size',
           title='(c) Marginal-load placement is not enough for every stage')
    ax = axes[1, 1]
    selected = ['home','k2','wide','b_cfg','c_n192','b_cfg_rx3','c_n192_rx3']
    first = {r['label']:r for r in data['metrics'] if r['case']=='h0_b1'}
    colors = ['#999999','#555555','#805aa0','#bf573a','#d98731','#2878a5','#289579']
    for label,color in zip(selected,colors):
        r = first[label]
        ax.scatter(r['access_wire_bit_mm']/1000,r['tx_plus_rx_payload_proxy_bits']/1024,
                   color=color,s=45)
        ax.annotate(label.replace('_cfg','').replace('_n192','').replace('_rx3',' / RX3'),
                    (r['access_wire_bit_mm']/1000,r['tx_plus_rx_payload_proxy_bits']/1024),
                    xytext=(4,3),textcoords='offset points',fontsize=8)
    ax.set(xlabel='Manufactured access wire (1,000 bit-mm / memory)',
           ylabel='TX + RX payload proxy (Kib / memory)',
           title='(d) RX3 costs another 24 Kib per k3 memory', xlim=(100,535), ylim=(15,103))
    for ax in (axes[0,0],axes[1,0],axes[1,1]):
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y', alpha=.15)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for ext in ('svg','pdf'):
        fig.savefig(output.with_suffix('.'+ext))
    plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    render(args.source,args.output)
