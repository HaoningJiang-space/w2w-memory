"""Plot the analytical residency choice beside measured finite-task controls."""
import argparse
from fractions import Fraction
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from w2w.theory.service_provisioning import credit_matched_split


def render(source, output):
    source, output = Path(source), Path(output)
    raw = source.read_bytes()
    data = json.loads(gzip.decompress(raw) if source.suffix == '.gz' else raw)
    plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none', 'pdf.fonttype': 42})
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.8), layout='constrained')
    windows = list(range(96, 209))
    for rate, label, color, style in ((Fraction(1, 2), 'A: shared 1/2 word/slot', '#1878aa', '-'),
                                      (Fraction(5, 8), 'B: shared 5/8 word/slot', '#c34e25', '--')):
        fractions = [float(Fraction(credit_matched_split(32, rate, n)['home_fraction'])) for n in windows]
        axes[0].plot(windows, fractions, label=label, color=color, linestyle=style, linewidth=2.2)
    axes[0].set(xlabel='Outstanding words per compute (N)', ylabel='Derived Home byte fraction',
                title='(a) Optimum of the steady-rate relaxation', ylim=(0.55, 1.04))
    axes[0].set_yticks([8/13, 2/3, 4/5, 1], ['8/13', '2/3', '4/5', '1'])
    for n, fraction in ((128, 4/5), (160, 2/3), (176, 8/13)):
        axes[0].scatter([n], [fraction], color='#222222', s=25, zorder=5)
        axes[0].annotate(str(n), (n, fraction), xytext=(3, 8), textcoords='offset points')
    axes[0].legend(loc='upper right', frameon=False, fontsize=8.5)
    selected = [r for r in data['results'] if r['case'] == 'dispersed9']
    for label, title, color, style in (
            ('k2', 'Home / k2 direct', '#777777', ':'),
            ('a_cfg', 'A, Home 2/3', '#1878aa', '-'),
            ('b_cfg', 'B, Home 8/13', '#c34e25', '--'),
            ('a_n128', 'A or B, Home 4/5', '#38915c', '-.'),
            ('wide', 'Wide k3 direct', '#725696', '-')):
        rows = sorted((r for r in selected if r['label'] == label), key=lambda r: r['window'])
        axes[1].plot([r['window'] for r in rows], [r['makespan_slots'] for r in rows],
                     label=title, color=color, linestyle=style, marker='o', linewidth=1.8)
    axes[1].set(xlabel='Outstanding words per compute (N)', ylabel='Task completion (native slots)',
                title='(b) Executed dispersed9 controls', xticks=[128, 160, 192], ylim=(46, 103))
    axes[1].legend(frameon=False, fontsize=8.5, loc='upper right', ncol=2)
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=0.18)
    output.parent.mkdir(parents=True, exist_ok=True)
    for extension in ('svg', 'pdf'):
        fig.savefig(output.with_suffix('.' + extension))
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    render(args.source, args.output)
