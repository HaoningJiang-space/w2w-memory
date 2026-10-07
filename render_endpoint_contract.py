"""Scientific contract plots and a sourced/candidate-separated data-path figure."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np


def save(fig,name):
    out=Path('research_figures/endpoint_contract');out.mkdir(parents=True,exist_ok=True)
    preview=Path('build/endpoint_sources');preview.mkdir(parents=True,exist_ok=True)
    fig.savefig(out/(name+'.svg'),bbox_inches='tight')
    fig.savefig(preview/(name+'.png'),dpi=160,bbox_inches='tight')
    plt.close(fig)


def plot_results(data):
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,3,figsize=(13,4.2),sharey=True)
    styles={'F':('#64748b',':'),'E':('#2563eb','-'),'M_direct':('#d97706','--'),'M_buffered':('#15803d','-.')}
    for ax,n in zip(axes,(1,2,4)):
        for contract,(color,style) in styles.items():
            rows=[r for r in data['rows'] if r['contract']==contract and r['active_outputs']==n and r['efficiency']==1.]
            ax.plot([r['alpha'] for r in rows],[r['total'] for r in rows],label=contract.replace('_',' '),
                    color=color,linestyle=style,linewidth=2.2 if contract!='M_buffered' else 1.5)
        ax.set_title(f'{n} active output'+('s' if n>1 else ''))
        ax.set_xlabel(r'Per-output peak / native service, $\alpha=\lambda/\mu$')
        ax.set_xlim(.25,1);ax.set_ylim(0,1.08);ax.set_xticks([.25,.5,.75,1]);ax.grid(alpha=.2)
        ax.axhline(1,color='#94a3b8',linewidth=.7)
    axes[0].set_ylabel(r'Total served complete bytes / $\mu$')
    axes[2].legend(loc='lower right',frameon=True)
    fig.suptitle('Endpoint contract envelope: one bank, four outputs, fixed byte classes',fontsize=14,y=1.02)
    fig.text(.5,-.04,'Zero switch overhead; buffered M overlaps E in the long-run relaxation. F fixes each output at 1/4.\n'
        'No wafer speedup or circuit calibration. Increasing alpha also increases provisioned output width.',ha='center',fontsize=9)
    fig.tight_layout();save(fig,'phase')


def datapath():
    fig,ax=plt.subplots(figsize=(13,8));ax.set_xlim(0,13);ax.set_ylim(0,8);ax.axis('off')
    def box(x,y,w,h,text,fc='#eff6ff',edge='#2563eb'):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.05',facecolor=fc,edgecolor=edge,linewidth=1.2))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=9)
    def arrow(x0,y0,x1,y1):ax.annotate('',xy=(x1,y1),xytext=(x0,y0),arrowprops=dict(arrowstyle='->',color='#334155',lw=1.3))
    ax.text(.2,7.65,'Public boundary: SeDRAM channel (functional abstraction of Section 2.1)',fontsize=14,weight='bold')
    for x,w,text in [(.2,2.0,'128 Mb array channel\nshared row state'),(2.65,2.1,'Sense / column select\nlocal data merge'),
                     (5.2,2.1,'Full-swing RWDL\n128 data bits'),(7.8,1.25,'HB'),(9.6,2.9,'Logic-side control / I/O\nRA, CA, BNKSELb\nCASRD / CASWR')]:
        box(x,6.3,w,.9,text)
    for a,b in [(2.2,2.65),(4.75,5.2),(7.3,7.8),(9.05,9.6)]:arrow(a,6.75,b,6.75)
    ax.text(.25,5.92,'Eight independent channels per 1 Gb unit; this does NOT establish four independent outputs within one channel.',fontsize=10)
    ax.plot([.2,12.7],[5.6,5.6],color='#94a3b8',linestyle='--')
    ax.text(.2,5.22,'Added candidates below: NOT implemented or measured in the cited SeDRAM design',fontsize=13,weight='bold',color='#92400e')
    ax.text(.25,4.75,'M-direct: one selected output occupies the delivery path',fontsize=11,weight='bold')
    box(.3,3.65,2.0,.8,'Complete-word source\nnative service mu','#fff7ed','#d97706')
    box(3.0,3.65,2.2,.8,'Selector + serializer\none output at a time','#fff7ed','#d97706')
    box(6.2,4.15,2.4,.65,'Driver / HB region 0\npeak lambda','#fff7ed','#d97706')
    box(6.2,3.05,2.4,.65,'Driver / HB region 1\npeak lambda','#fff7ed','#d97706')
    arrow(2.3,4.05,3.,4.05);arrow(5.2,4.05,6.2,4.45);arrow(5.2,4.05,6.2,3.4)
    ax.text(9.,3.95,'sum(time fractions) <= 1\nf_e <= lambda * t_e\nTotal <= lambda when lambda < mu',va='center',fontsize=10)
    ax.text(.25,2.55,'M-buffered: serialize native service, drain output FIFOs independently',fontsize=11,weight='bold')
    box(.3,1.35,2.,.8,'Complete-word source\nnative service mu','#f0fdf4','#15803d')
    box(3.,1.35,2.2,.8,'Owner arbitration\nfull-word demux','#f0fdf4','#15803d')
    box(6.2,1.95,2.4,.65,'FIFO 0 -> driver / HB 0\npeak lambda','#f0fdf4','#15803d')
    box(6.2,.85,2.4,.65,'FIFO 1 -> driver / HB 1\npeak lambda','#f0fdf4','#15803d')
    arrow(2.3,1.75,3.,1.75);arrow(5.2,1.75,6.2,2.25);arrow(5.2,1.75,6.2,1.15)
    ax.text(9.,1.65,'FIFO capacity: sum(D_e * W) bits\nf_e <= mu * t_e; f_e <= lambda\nParallel drain; native bank not replicated',va='center',fontsize=10)
    ax.text(.25,.32,'Both candidates need command ownership, response tags and real cross-reticle HB paths.\n'
        'W = 128 is a published interface example; endpoint widths, buffer depths and effective mu remain design inputs.',fontsize=9)
    save(fig,'datapath')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('input');args=parser.parse_args()
    plot_results(json.loads(Path(args.input).read_text()));datapath()
