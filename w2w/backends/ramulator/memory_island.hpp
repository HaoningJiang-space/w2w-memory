// Restricted one-domain service frontend. Array service remains Ramulator.
// Ordering is callback -> scheduled arrivals -> Gateway -> atom issue, exactly
// as VerticalRWDL.advance(). A sequence number orders same-time future events.
#include <algorithm>
#include <array>
#include <deque>
#include <map>
#include <queue>
#include <tuple>

class MemoryServiceIsland {
  using U = uint64_t;
  using Event = std::array<U,7>; // time, sequence, kind, request, offset, origin, unused
  using Log = std::array<U,8>; // time, kind, request, a, b, c, d, unused
  struct RequestState {
    U size, cursor, address, raw=0, received=0, prefix=0, supplied=0;
    bool started=false, first=false;
    std::set<U> valid;
  };
  IncrementalMemory& memory;
  U dram,logic,transport,pipeline,cdc,access,return_limit,slots,tx_limit,window,flit,header;
  std::string policy;
  std::map<U,RequestState> requests;
  std::deque<U> queue;
  std::map<U,std::pair<U,U>> tickets;
  std::deque<Event> aggregate;
  std::priority_queue<Event,std::vector<Event>,std::greater<Event>> future;
  std::vector<Log> logs;
  std::vector<std::array<U,3>> ready;
  std::vector<U> done;
  U now=0,serial=0,command_free=0,access_free=0,ack_free=0;
  U command_live=0,command_peak=0,ack_pending=0,ack_peak=0;
  U descriptors=0,descriptor_peak=0,pool_live=0,pool_peak=0;
  U reserved=0,reservation_peak=0,rr=0;
  U accepted=0,completed=0,atoms=0,raw_atoms=0,rejected=0;
  U reservation_stalls=0,queue_stalls=0,command_stalls=0;
  U gateway_bytes=0,gateway_busy=0,gateway_peak=0;
  U collection_ps=0,cdc_ps=0,gateway_ps=0,first_tail=0,last_tail=0;
  U steps=0,dram_ticks=0,host_calls=0;
  int64_t selected_row=-1;
  bool begun=false,observable=false;

  static U edge(U at,U p) {return (at+p-1)/p*p;}
  void schedule(U at,U kind,U key,U offset,U origin) {
    future.push({at,++serial,kind,key,offset,origin,0});
  }
  void log(U at,U kind,U key,U a=0,U b=0,U c=0,U d=0) {
    logs.push_back({at,kind,key,a,b,c,d,0});
  }
  void phase(U at) {
    ++steps;now=at;
    U target=at/dram;
    auto callbacks=memory.advance(target);
    dram_ticks=target;
    for(auto [ticket,cycle]:callbacks) {
      auto found=tickets.find(ticket);
      if(found==tickets.end())throw std::runtime_error("Island callback ticket missing");
      auto [key,offset]=found->second;tickets.erase(found);
      auto& row=requests.at(key);U tail=cycle*dram, hb=tail+transport;
      U sample=(edge(hb,logic)/logic+cdc)*logic;
      collection_ps+=transport;cdc_ps+=sample-hb;++row.raw;++raw_atoms;
      if(row.raw==1 || row.raw==row.size/16)
        log(tail-dram,row.raw==1?7:8,key,hb);
      if(!first_tail)first_tail=tail;
      last_tail=tail;schedule(sample,2,key,offset,tail);
    }
    while(!future.empty() && future.top()[0]<=at) {
      auto event=future.top();future.pop();
      auto [when,sequence,kind,key,offset,origin,unused]=event;
      if(kind==3) { // ACK ready
        ++ack_pending;ack_peak=std::max(ack_peak,ack_pending);
        if(ack_pending>tx_limit)throw std::runtime_error("Island finite ACK overflow");
        U start=edge(std::max(when,ack_free),logic),end=start+2*logic;
        ack_free=end;ack_bytes+=8;log(start,3,key,end,end+2*logic,origin,when);
        schedule(end+2*logic,4,key,0,origin);
      } else if(kind==4) {
        --ack_pending;--command_live;--descriptors;
        log(when,4,key);observable=true;
      } else if(kind==1) {
        queue.push_back(key);log(when,5,key);
      } else if(kind==2) {
        aggregate.push_back(event);gateway_peak=std::max(gateway_peak,U(aggregate.size()*16));
      } else if(kind==5) {
        auto& row=requests.at(key);
        --reserved;++row.received;ready.push_back({key,offset,when});gateway_ps+=when-origin;
        row.valid.insert(offset/16);
        while(row.prefix<row.size && row.valid.count(row.prefix/16))row.prefix+=16;
        U eligible=row.prefix<row.size?(row.prefix+header)/flit:(row.size+header+flit-1)/flit;
        if(!row.first || eligible!=row.supplied)observable=true;
        row.first=true;row.supplied=eligible;
        if(row.received*16==row.size) {
          done.push_back(key);--pool_live;++completed;requests.erase(key);observable=true;
        }
      } else throw std::runtime_error("Unknown island event");
    }
    if(at%logic==0) {
      U count=std::min<U>(aggregate.size(),gateway_width);
      if(count)++gateway_busy;
      while(count--) {
        auto item=aggregate.front();aggregate.pop_front();gateway_bytes+=16;
        schedule(at+(1+access)*logic,5,item[3],item[4],item[5]);
      }
    }
    if(at%dram==0 && !queue.empty()) {
      if(reserved>=return_limit) {++reservation_stalls;return;}
      U index=0,span=std::min<U>(window,queue.size());
      if(policy=="round_robin")index=rr%span;
      else if(policy=="row_batched" && selected_row>=0)
        for(U i=0;i<span;++i)if(requests.at(queue[i]).address/64==U(selected_row)){index=i;break;}
      U key=queue[index];auto& row=requests.at(key);
      if(!memory.send(atoms,0,row.address)) {++queue_stalls;++rejected;return;}
      if(!row.started) {row.started=true;log(at,6,key);}
      tickets.emplace(atoms++,std::pair<U,U>{key,row.cursor});++reserved;
      reservation_peak=std::max(reservation_peak,reserved);selected_row=row.address/64;
      rr=(index+1)%window;row.cursor+=16;++row.address;
      if(row.cursor>=row.size) {
        queue.erase(queue.begin()+index);
        U ack=edge(at+(1+pipeline)*logic,logic);
        schedule(ack,3,key,0,at);log(at,2,key,ack);
      }
    }
  }
  U gateway_width;
 public:
  explicit MemoryServiceIsland(IncrementalMemory& m,nb::dict cfg):memory(m) {
    auto get=[&](const char* name){return nb::cast<U>(cfg[name]);};
    dram=get("dram");logic=get("logic");transport=get("transport");pipeline=get("pipeline");
    cdc=get("cdc");access=get("access");return_limit=get("return_atoms");slots=get("slots");
    tx_limit=get("tx_limit");window=get("window");gateway_width=get("gateway_atoms");
    flit=get("flit_bytes");header=get("header_bytes");policy=nb::cast<std::string>(cfg["policy"]);
    if(dram!=3760 || logic!=1000 || !return_limit || !slots || !tx_limit || !window || !gateway_width
       || flit!=128 || header!=16 || (policy!="fifo" && policy!="row_batched" && policy!="round_robin"))
      throw std::runtime_error("Unsupported memory island contract");
  }
  bool submit(U key,U size,U address,U at) {
    if(!begun || at!=now || at%dram || size==0 || size%32 || size>4096 || requests.count(key))
      throw std::runtime_error("Invalid island descriptor or external input clock");
    if(pool_live>=slots)return false;
    if(command_live+1>tx_limit || descriptors>=32) {++command_stalls;return false;}
    requests.emplace(key,RequestState{size,0,address});++accepted;++pool_live;pool_peak=std::max(pool_peak,pool_live);
    U start=edge(std::max(at,access_free),logic),end=start+2*logic;
    access_free=end;U access_end=end+access*logic;log(start,0,key,end,access_end);
    start=edge(std::max(access_end,command_free),logic);end=start+4*logic;command_free=end;
    U arrival=edge(end+(1+pipeline)*logic+2*dram,dram);
    ++command_live;++descriptors;command_peak=std::max(command_peak,command_live);
    descriptor_peak=std::max(descriptor_peak,descriptors);
    log(start,1,key,end,arrival,access_end);schedule(arrival,1,key,0,at);
    return true;
  }
  nb::dict advance(U target,bool until_observable=false) {
    if(begun && target<now)throw std::runtime_error("Nonmonotonic island time");
    ++host_calls;observable=false;
    if(!begun) {begun=true;phase(0);}
    while(now<target) {
      U next=std::min((now/dram+1)*dram,(now/logic+1)*logic);
      if(!future.empty())next=std::min(next,future.top()[0]);
      next=std::min(next,target);phase(next);
      if(until_observable && observable)break;
    }
    nb::dict out;out["stop_ps"]=now;
    out["ready"]=nb::cast(std::exchange(ready,{}));out["complete"]=nb::cast(std::exchange(done,{}));
    out["events"]=nb::cast(std::exchange(logs,{}));out["observable"]=observable;return out;
  }
  nb::dict ledger() const {
    nb::dict r;
    r["accepted"]=accepted;r["completed"]=completed;r["atoms"]=atoms;r["raw_atoms"]=raw_atoms;r["rejected"]=rejected;
    r["pending"]=requests.size()+tickets.size()+future.size()+aggregate.size();
    r["pending_atoms"]=tickets.size();r["reserved"]=reserved;r["reservation_peak"]=reservation_peak;
    r["pool_live"]=pool_live;r["pool_peak"]=pool_peak;r["command_live"]=command_live;r["command_peak"]=command_peak;
    r["ack_pending"]=ack_pending;r["ack_peak"]=ack_peak;r["descriptors"]=descriptors;r["descriptor_peak"]=descriptor_peak;
    r["command_stalls"]=command_stalls;r["queue_stalls"]=queue_stalls;r["reservation_stalls"]=reservation_stalls;
    r["gateway_bytes"]=gateway_bytes;r["gateway_busy"]=gateway_busy;r["gateway_peak"]=gateway_peak;
    r["collection_ps"]=collection_ps;r["cdc_ps"]=cdc_ps;r["gateway_ps"]=gateway_ps;
    r["first_tail"]=first_tail;r["last_tail"]=last_tail;
    r["command_bytes"]=accepted*16;
    r["ack_bytes"]=ack_bytes;r["steps"]=steps;r["dram_ticks"]=dram_ticks;r["host_calls"]=host_calls;
    return r;
  }
  U ack_bytes=0;
};
