"""Conceptual interface-cut choices, not a DRAM floorplan or measured circuit."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def draw(output='research_figures/bank_hb_boundary'):
    plt.rcParams['svg.fonttype']='none'
    fig,axes=plt.subplots(1,2,figsize=(11,6.7),layout='constrained')
    blue='#e8f1fc';orange='#fff0d9';green='#e6f4ee'
    def box(ax,x,y,w,h,label,color):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.025',facecolor=color,edgecolor='#526173'))
        ax.text(x+w/2,y+h/2,label,ha='center',va='center',fontsize=10)
    def arrow(ax,start,end):
        ax.annotate('',end,start,arrowprops=dict(arrowstyle='->',color='#526173',lw=1.4))
    for ax in axes:
        ax.set(xlim=(0,10),ylim=(-.7,10));ax.axis('off')
        ax.axhline(3.45,color='#758da1',ls='--',lw=1,zorder=0)
        ax.text(.2,4.05,'MEMORY RETICLE',fontsize=8,color='#526173')
        ax.text(.2,2.8,'LOGIC',fontsize=8,color='#526173')
        box(ax,1,8.35,8,1.05,'Banks / subarrays\nSense amps + column selection',blue)
        box(ax,1.6,6.7,6.8,.85,'Exported electrical endpoints\ne.g. buffered digital channels',green)
        arrow(ax,(5,8.35),(5,7.55))
    a,b=axes
    a.set_title('A. Candidate switching before HB',fontsize=13,pad=12)
    box(a,1.5,4.8,7,1.05,'Steering + buffers\nControl ownership must be defined',orange)
    arrow(a,(5,6.7),(5,5.85))
    for x,p,c in [(1.4,'HB0','Compute reticle C0'),(6.,'HB1','Compute reticle C1')]:
        box(a,x,3.1,2.6,.65,p,green);arrow(a,(5,4.8),(x+1.3,3.75))
        box(a,x-.3,1.25,3.2,1.05,c+'\nReceiver / controller',blue)
        arrow(a,(x+1.3,3.1),(x+1.3,2.3))
    a.text(5,.35,'Each HB region needs a legal opposite-wafer landing.',ha='center',fontsize=8)
    b.set_title('B. Candidate switching after HB',fontsize=13,pad=12)
    box(b,3.1,3.1,3.8,.65,'Fixed HB landing',green)
    arrow(b,(5,6.7),(5,3.75))
    box(b,1.5,1.3,7,1.05,'Logic-side steering / consumers\ninside ONE compute reticle',orange)
    arrow(b,(5,3.1),(5,2.35))
    b.text(5,.35,'Another compute reticle needs an explicit physical path.',ha='center',fontsize=8)
    fig.suptitle('Where is the memory interface cut?',fontsize=17)
    fig.supxlabel('Conceptual read paths only. Write, command/address, clock and status paths remain required.\nOrange blocks are research candidates; this is not a manufactured SeDRAM layout.',fontsize=9)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    for suffix in ['svg','png']:fig.savefig(out/('boundary.'+suffix),dpi=160)
    p=out/'boundary.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text().splitlines())+'\n')
    plt.close(fig)

if __name__=='__main__':draw()
