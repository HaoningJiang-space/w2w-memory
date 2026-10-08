"""Occupancy contract for bank-local TX, held beat, elastic link and RTL-sized RX.

This is a count-level model, not RTL/payload equivalence or physical timing.
Each link stage advertises space from its own pre-edge occupancy, avoiding a
combinational ready chain across all stages. Stage payload must be charged.
"""
from fractions import Fraction
from math import gcd


def beat_path_period(width, source_depth, stages=0, stage_slots=2, sink_ready=(1,)):
    if (type(width)!=int or width not in range(32,257,32) or source_depth not in (1,2)
            or type(stages)!=int or stages<0 or stage_slots not in (1,2)
            or not sink_ready or any(type(v)!=int or v not in (0,1) for v in sink_ready)):
        raise ValueError('Invalid beat path contract')
    out=width//32
    capacity=(256+width-gcd(256,width))//32
    # fifo words, head offset in units, held beat units, per-stage beats, RX units
    state=(0,0,0,tuple(() for _ in range(stages)),0)
    admitted=delivered=accepted_units=0
    seen,history={},[]
    peaks=dict(source_words=0,held_units=0,link_units=0,rx_units=0)
    for tick in range(100000):
        key=(tick%len(sink_ready),state)
        if key in seen:
            first,old=seen[key]
            period=tick-first
            delta=(admitted-old[0],delivered-old[1],accepted_units-old[2])
            if delta[0]!=delta[1] or delta[2]!=8*delta[1]:
                raise ValueError('Periodic complete-word conservation failed')
            return dict(width_bits=width,source_depth=source_depth,link_stages=stages,
                stage_slots=stage_slots,sink_ready=list(sink_ready),warmup_slots=first,period_slots=period,
                words_per_period=delta[1],words_per_slot=str(Fraction(delta[1],period)),
                periodic_states=history[first:tick],peak_occupancy=peaks,
                payload_bits=dict(source=source_depth*256,held_beat=width,
                                  link=stages*stage_slots*width,rx=capacity*32),
                scope='Isolated count-level recurrent contract; local pre-edge space; no payload/RTL/timing equivalence')
        seen[key]=(tick,(admitted,delivered,accepted_units))
        history.append(key)
        count,offset,held,pipe,rx=state
        pop_word=rx>=8 and bool(sink_ready[tick%len(sink_ready)])
        rx_accept=rx-(8 if pop_word else 0)+out<=capacity
        space=tuple(len(q)<stage_slots for q in pipe)
        destination=space[0] if stages else rx_accept
        advance=not held or destination
        native_push=count<source_depth  # same no-pop-lookahead rule as cse_fifo
        view=count+int(native_push)
        emitted=min(out,8*view-offset) if advance and view else 0
        fifo_pop=offset+emitted>=8
        next_offset=(offset+emitted)%8
        next_count=view-int(fifo_pop)
        next_held=emitted if advance else held
        updated=[]
        for i,q in enumerate(pipe):
            row=list(q)
            downstream=space[i+1] if i+1<stages else rx_accept
            if q and downstream:
                row.pop(0)
            incoming=held if i==0 else (pipe[i-1][0] if pipe[i-1] else 0)
            if incoming and space[i]:
                row.append(incoming)
            updated.append(tuple(row))
        incoming=pipe[-1][0] if stages and pipe[-1] else (held if not stages else 0)
        received=incoming if rx_accept else 0
        next_rx=rx-(8 if pop_word else 0)+received
        admitted+=int(native_push);delivered+=int(pop_word);accepted_units+=received
        state=(next_count,next_offset,next_held,tuple(updated),next_rx)
        link_units=sum(sum(q) for q in updated)
        if (8*admitted!=8*delivered+next_count*8-next_offset+next_held+link_units+next_rx
                or not 0<=next_count<=source_depth or not 0<=next_rx<=capacity
                or any(len(q)>stage_slots or any(not 0<n<=out for n in q) for q in updated)):
            raise ValueError('Per-edge word/unit conservation or capacity failed')
        peaks['source_words']=max(peaks['source_words'],next_count)
        peaks['held_units']=max(peaks['held_units'],next_held)
        peaks['link_units']=max(peaks['link_units'],link_units)
        peaks['rx_units']=max(peaks['rx_units'],next_rx)
    raise ValueError('No finite recurrence found')
