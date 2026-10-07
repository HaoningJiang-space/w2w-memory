"""Render captured-routing diagnostics; bands are sensitivity ranges, not CIs."""
import argparse
import csv
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def render(source, output):
    path = Path(source)
    raw = path.read_bytes()
    data = json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    keys = ('distinct_experts_mean', 'weight_read_reuse_saved', 'active_compute_mean',
            'peak_to_mean_demand', 'active_client_idle_partner_fraction',
            'occupancy_conditioned_idle_partner_null', 'bank_only_sequential_bound_ratio',
            'idle_partner_streak_mean_decode_steps')
    table = []
    for batch in data['plan']['batch_sizes']:
        rows = [r for r in data['results'] if r['batch_size'] == batch]
        base = [r for r in rows if r['mapping_seed'] is None]
        row = dict(batch_size=batch)
        for key in keys:
            row[key] = float(np.mean([r[key] for r in base]))
            row[key + '_sensitivity_min'] = min(r[key] for r in rows)
            row[key + '_sensitivity_max'] = max(r[key] for r in rows)
        table.append(row)
    with (output / 'batch_metrics.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    (output / 'batch_metrics.json').write_text(json.dumps(dict(
        base='expert id modulo 36; mean of four fixed cohort orderings',
        bands='Range over four orderings and three frozen mappings; not a confidence interval',
        rows=table), indent=2) + '\n')
    x = np.array([r['batch_size'] for r in table])
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.7), constrained_layout=True)
    def line(ax, key, label, scale=1, color=None):
        y = np.array([r[key] for r in table]) * scale
        low = np.array([r[key + '_sensitivity_min'] for r in table]) * scale
        high = np.array([r[key + '_sensitivity_max'] for r in table]) * scale
        item, = ax.plot(x, y, 'o-', label=label, color=color, markersize=4)
        ax.fill_between(x, low, high, color=item.get_color(), alpha=.12)
    line(axes[0], 'weight_read_reuse_saved', 'Within-batch weight reuse', 100)
    line(axes[0], 'active_compute_mean', 'Active compute / 36', 100/36)
    axes[0].set(ylabel='Percent', title='Reuse rises; spatial sparsity falls', ylim=(0, 105))
    line(axes[1], 'active_client_idle_partner_fraction', 'Observed fixed partners', 100)
    axes[1].plot(x, [r['occupancy_conditioned_idle_partner_null']*100 for r in table],
                 '--', color='black', label='Occupancy-conditioned null')
    axes[1].set(ylabel='Active clients with idle partner (%)', title='Most opportunity follows occupancy')
    line(axes[2], 'bank_only_sequential_bound_ratio', 'Home bound / pair bound')
    axes[2].axhline(1, color='gray', linestyle=':')
    axes[2].set(ylabel='Ratio of memory-only time bounds', title='Diagnostic; not executed speedup')
    for ax in axes:
        ax.set_xscale('log', base=2)
        ax.set_xticks(x, [str(v) for v in x])
        ax.set_xlabel('Fixed decode cohort size')
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.savefig(output / 'batch_reuse_and_sharing.svg')
    fig.savefig(output / 'batch_reuse_and_sharing.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    render(args.summary, args.output)
