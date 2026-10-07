"""Plot audited read completion values; never import raw traces or run solvers."""
from pathlib import Path


def render(report, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    primary = max(r['outstanding'] for r in report['rows'])
    groups = sorted({r['group'] for r in report['rows']})
    fig, axes = plt.subplots(1, len(groups), figsize=(11.5, 3.6), constrained_layout=True,
                            squeeze=False)
    names = {0: 'Home', 1: 'k2 direct', 2: 'k3 direct', 6: 'Configurable B'}
    for ax, group in zip(axes[0], groups):
        for index, label in names.items():
            rows = sorted((r for r in report['rows'] if r['group'] == group and
                           r['design_index'] == index and r['outstanding'] == primary),
                          key=lambda r: r['batch_size'])
            ax.plot([r['batch_size'] for r in rows], [r['home_relative_ratio'] for r in rows],
                    'o-', label=label, markersize=4)
        ax.set(xscale='log', xlabel='Fixed decode cohort', ylabel='Home / design read time',
               title=f"{group}: layer {rows[0]['layer']}, step {rows[0]['decode_step']}")
        ax.set_xticks([1, 4, 16], ['1', '4', '16'])
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.savefig(output / 'read_completion.svg')
    fig.savefig(output / 'read_completion.png', dpi=160)
    plt.close(fig)


