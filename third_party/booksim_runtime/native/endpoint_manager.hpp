// Endpoint-only extension; linked with the reviewed hooks in an isolated build.
// Router scheduling, internal buffers, routing, links and packet generation are reused.
#include <deque>
#include <set>
#include <algorithm>
#include <list>
#include "iq_router.hpp"

class BoundaryTrafficManager : public OnlineTrafficManager {
    BookSimConfig original;
    bool enabled=false, bounded=false, streaming=false;
    int slots=0;
    std::vector<int> supplied, sent;
    std::map<int,int> ordinals;
    std::map<int,std::pair<int,int>> held; // flit -> destination, VC
    std::vector<int> occupied;
    std::vector<std::deque<int>> returns;
    std::vector<json> progress;
    std::vector<uint64_t> unsupplied_head, ready_behind, ready_behind_with_credit, ready_head_credit_wait;
    std::map<int,uint64_t> unsupplied_by_message, ready_behind_by_message;
    std::vector<std::set<int>> ready_sources;
    std::set<int> ready_nodes;
    int arbitration_slots=0;
    std::vector<std::set<int>> arbitration_live;
    std::vector<std::list<Flit*>> parked;
    std::vector<uint64_t> ready_selections;

    void _EndpointPrepareInject() override {
        // One finite source selector, one existing physical injection port.
        // All packets here are single-cell, so selecting another message does
        // not abandon a wormhole packet or duplicate a VC/credit resource.
        for(int node:ready_nodes) {
            auto &queue=_partial_packets[node][0];
            int candidate=-1;
            // Submit assigns monotonically increasing IDs. This chooses the
            // oldest ADMITTED message among supplied candidates, not the one
            // that has waited longest since its payload became ready.
            for(int mid:arbitration_live[node]) {
                if(sent[mid]<supplied[mid]) {candidate=mid;break;}
            }
            if(candidate<0 || (!queue.empty() && queue.front()->mid==candidate)) continue;
            ++ready_selections[node];
            auto it=std::find_if(queue.begin(),queue.end(),[candidate](Flit *f){return f->mid==candidate;});
            if(it!=queue.end()) {queue.splice(queue.begin(),queue,it);continue;}
            // Native trace generation normally waits for the old queue to
            // empty. Park those already-paid NI cells, expose one selected
            // admitted message, then use the unchanged native generator.
            parked[node].splice(parked[node].end(),queue);
            auto &pending=ready_messages[node];
            std::pair<long,long> selected;
            std::vector<std::pair<long,long>> remaining;
            bool found=false;
            while(!pending.empty()) {
                auto item=pending.top();pending.pop();
                if(item.second==candidate) {selected=item;found=true;}
                else remaining.push_back(item);
            }
            if(!found) throw std::runtime_error("Ready message is absent from native source stages");
            for(auto item:remaining) pending.push(item);
            // This is only the generator priority, not the recorded original
            // admission timestamp; selected traffic was supplied already.
            pending.push({-1,selected.second});
        }
    }
    void _EndpointRestoreInject() override {
        for(int node:ready_nodes)
            _partial_packets[node][0].splice(_partial_packets[node][0].end(),parked[node]);
    }

    bool _EndpointCanInject(Flit const *f) override {
        if (!streaming) return true;
        bool ready=sent.at(f->mid)<supplied.at(f->mid);
        auto *buffer=_buf_states[f->src][f->subnetwork];
        bool credit=buffer->IsAvailableFor(0) && !buffer->IsFullFor(0);
        if (ready) {
            if (!credit) ++ready_head_credit_wait[f->src];
            return true;
        }
        ++unsupplied_head[f->src];++unsupplied_by_message[f->mid];
        // Trace mode generates the next message only after its partial queue
        // empties. Count supplied admitted messages in BOTH source stages.
        if (!ready_sources[f->src].empty()) {
            ++ready_behind[f->src];++ready_behind_by_message[f->mid];
            if (credit) ++ready_behind_with_credit[f->src];
        }
        return false;
    }
    void _EndpointInjected(Flit const *f) override {
        if (!streaming) return;
        int ordinal=sent.at(f->mid)++;
        if (sent.at(f->mid)==supplied.at(f->mid)) ready_sources[f->src].erase(f->mid);
        if(sent.at(f->mid)==msg_packets[f->mid]) arbitration_live[f->src].erase(f->mid);
        ordinals[f->id]=ordinal;
        progress.push_back({{"event","inject"},{"id",f->mid},{"flit",f->id},
            {"ordinal",ordinal},{"cycle",_time+1},{"source",f->src}});
    }
    void _EndpointCredit(Flit const *f, int subnet, int node) override {
        if (!enabled || !bounded) { TrafficManager::_EndpointCredit(f,subnet,node); return; }
        if (held.count(f->id)) throw std::runtime_error("Repeated held endpoint credit");
        held[f->id]={node,f->vc};
        if (++occupied[node]>slots) throw std::runtime_error("Endpoint receive slots exceeded");
    }
    void _RetireFlit(Flit *f,int node) override {
        int mid=f->mid, fid=f->id;
        OnlineTrafficManager::_RetireFlit(f,node);
        if (!streaming) return;
        auto event=message_flits.at(mid).back();
        event["ordinal"]=ordinals.at(fid);
        progress.push_back({{"event","receive"},{"id",mid},{"flit",fid},
            {"ordinal",ordinals.at(fid)},{"cycle",_time+1},{"destination",node},{"record",event}});
        ordinals.erase(fid);
        // Execution state is bounded by live traffic. The completed reply and
        // current progress batch already own their copies of these records.
        if(msg_flits_remaining.at(mid)==0) message_flits[mid]=json::array();
    }
    void ReturnCredits() {
        for (int node=0;node<_nodes;++node) if (!returns[node].empty()) {
            Credit *c=Credit::New(); c->AddVC(returns[node].front());
            returns[node].pop_front(); _net[0]->WriteCredit(c,node);
        }
    }
    void Step() override { ReturnCredits(); OnlineTrafficManager::Step(); }
public:
    BoundaryTrafficManager(const BookSimConfig &config,const std::vector<Network*> &net)
        : OnlineTrafficManager(config,net), original(config), occupied(_nodes), returns(_nodes),
          unsupplied_head(_nodes),ready_behind(_nodes),ready_behind_with_credit(_nodes),
          ready_head_credit_wait(_nodes),ready_sources(_nodes),arbitration_live(_nodes),parked(_nodes),ready_selections(_nodes) {}
    bool Idle() const override {
        if (!held.empty()) return false;
        for (const auto &q:returns) if (!q.empty()) return false;
        return OnlineTrafficManager::Idle();
    }
    json Submit(const json &r) override {
        int source=r.at("source"),mid=r.at("id");
        if(ready_nodes.count(source) && static_cast<int>(arbitration_live[source].size())>=arbitration_slots)
            throw std::runtime_error("Finite source arbitration slots exceeded");
        auto reply=OnlineTrafficManager::Submit(r);
        supplied.push_back(streaming?0:r.at("flits").get<int>()); sent.push_back(0);
        if(ready_nodes.count(source)) arbitration_live[source].insert(mid);
        return reply;
    }
    json BoundaryCommand(const json &r) {
        std::string command=r.at("command");
        if (r.at("cycle").get<int>()!=_time) throw std::runtime_error("Endpoint clock mismatch");
        if (command=="boundary") {
            if (_time!=0 || rc_trace_instructions || enabled || _vcs!=1 ||
                original.GetStr("buffer_policy")!="private")
                throw std::runtime_error("Boundary mode requires empty one-VC private-buffer trace");
            slots=r.at("rx_slots"); bounded=r.at("bounded");
            streaming=r.at("streaming");
            arbitration_slots=r.value("ready_slots",0);
            for(int node:r.value("ready_nodes",std::vector<int>{})) {
                if(node<0 || node>=_nodes || arbitration_slots<1 || arbitration_slots>64 || !streaming)
                    throw std::runtime_error("Invalid finite ready arbiter");
                ready_nodes.insert(node);
            }
            if (bounded && !streaming) throw std::runtime_error("Bounded endpoint needs progress callbacks");
            if (slots<=0) throw std::runtime_error("Invalid receive slots");
            BookSimConfig sink(original);sink.Assign("vc_buf_size",slots);sink.Assign("buf_size",-1);
            for (auto *ch:_net[0]->GetEject()) {
                auto *router=dynamic_cast<IQRouter*>(const_cast<Router*>(ch->GetSource()));
                if (!router) throw std::runtime_error("Endpoint requires IQRouter");
                router->ConfigureEndpointSink(sink,ch->GetSourcePort());
            }
            enabled=true;
        } else if (command=="supply") {
            int mid=r.at("id"),count=r.at("flits");
            if (!enabled || mid<0 || mid>=static_cast<int>(supplied.size()) ||
                count<=0 || supplied[mid]+count>msg_packets[mid])
                throw std::runtime_error("Invalid or excess supplied payload");
            supplied[mid]+=count;
            if (sent[mid]<supplied[mid]) ready_sources[msg_source[mid]].insert(mid);
        } else if (command=="commit") {
            int fid=r.at("flit");
            if (!enabled || !bounded || !held.count(fid)) throw std::runtime_error("Unknown committed flit");
            auto item=held.at(fid);held.erase(fid);
            if (--occupied[item.first]<0) throw std::runtime_error("Negative endpoint occupancy");
            returns[item.first].push_back(item.second);
        } else throw std::runtime_error("Unknown boundary command");
        return {{"ok",true},{"cycle",_time}};
    }
    json Advance(int limit) override {
        if (!enabled) return OnlineTrafficManager::Advance(limit);
        if (limit<_time || limit>1000000000) throw std::runtime_error("Invalid advance boundary");
        finished.clear();progress.clear();
        while (_time<limit) {
            if (Idle()) { skipped+=limit-_time;_time=limit;global_current_cycle=_time;break; }
            Step();
            if (!progress.empty() || !finished.empty()) break;
        }
        return {{"ok",true},{"cycle",_time},{"completed",finished},{"progress",progress},{"idle",Idle()}};
    }
    json Close() {
        auto reply=OnlineTrafficManager::Close();
        reply["source_pressure"]={{"arbitration",ready_nodes.empty()?"FIFO; no bypass of unsupplied head":"bounded oldest-admitted among ready per selected source; one physical injection"},
            {"ready_slots",arbitration_slots},{"ready_selections",ready_selections},
            {"unsupplied_head_cycles",unsupplied_head},{"ready_behind_unsupplied_cycles",ready_behind},
            {"ready_behind_with_injection_credit_cycles",ready_behind_with_credit},
            {"ready_head_credit_wait_cycles",ready_head_credit_wait},
            {"unsupplied_by_message",unsupplied_by_message},
            {"ready_behind_by_message",ready_behind_by_message}};
        return reply;
    }
};
