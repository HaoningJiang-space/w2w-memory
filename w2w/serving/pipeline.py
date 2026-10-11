"""Finite explicitly priced inter-stack transport, driven by real completed stages."""
from collections import Counter
from math import ceil


class PipelineLinks:
    def __init__(self,profile):
        self.profile=profile;self.tx=Counter();self.rx=Counter();self.links=Counter();self.events=[]

    def transfer(self,source,destination,payload,ready_ps,*,window,kind):
        p=self.profile
        if payload<1 or payload>32*p.hidden*2:raise ValueError('Inter-stage batch exceeds existing declared finite transfer buffers')
        chunks=[min(p.inter_stage_packet_bytes,payload-i) for i in range(0,payload,p.inter_stage_packet_bytes)]
        headers=16*len(chunks);wire=sum(ceil((n+16)/128)*128 for n in chunks)
        start=ceil(max(ready_ps,self.tx[source],self.rx[destination],self.links[source,destination])/1000)*1000
        tx_end=start+ceil(wire/p.inter_stage_bytes_per_ns)*1000
        # Quiescent endpoints stream payload directly into the reserved RX
        # SRAM at the same 128 B/cycle. No free additional NI payload buffer.
        arrival=tx_end+p.inter_stage_latency_ps
        self.tx[source]=tx_end;self.rx[destination]=arrival;self.links[source,destination]=arrival
        e=dict(source=source,destination=destination,payload_bytes=payload,header_bytes=headers,wire_bytes=wire,
            ready_ps=ready_ps,start_ps=start,tx_end_ps=tx_end,committed_ps=arrival,window=window,kind=kind,
            source_sram_read_bytes=payload,destination_sram_write_bytes=payload,source_read_peak_bytes=128,
            destination_write_peak_bytes=128,sideband_bits=64,wire_bits=wire*8+(wire//128)*64)
        self.events.append(e);return arrival
