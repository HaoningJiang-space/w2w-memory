"""Pure summaries of completed system records; no execution or hidden input paths."""


def summarize(result):
    events=result['events']
    read_ready,reads,allocations,inputs={},{},{},{}
    for e in events:
        if e['kind']=='read_issue':reads[e['request']]=e['task']
        elif e['kind']=='native_ready':read_ready[reads[e['request']]]=e['time_ps']
        elif e['kind']=='task_allocate':allocations[e['task']]=e['time_ps']
        elif e['kind']=='data_deliver':
            edge=next(x for x in result['graph']['data'] if x['id']==e['edge'])
            inputs[edge['consumer']]=e['time_ps']
    delivered={}
    for e in events:
        if e['kind']=='read_deliver':delivered[e['task']]=e['time_ps']
    links={l['id']:l for l in result['spec']['links']}
    busiest=sorted((dict(link=k,kind=links[k]['kind'],flits=v,
                         busy_ps=v*links[k]['period_ps'],
                         utilization=v*links[k]['period_ps']/result['makespan_ps'])
                     for k,v in result['network']['link_flits'].items()),
                    key=lambda r:r['busy_ps'],reverse=True)[:10]
    timelines={key:dict(allocated_ps=allocations[key],last_native_ready_ps=read_ready.get(key),
                        last_read_delivery_ps=delivered.get(key),last_input_delivery_ps=inputs.get(key),**row)
               for key,row in result['tasks'].items()}
    return dict(makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],
        native=result['native'],network=result['network'],physical=result['physical'],
        compute_busy_ps=result['compute_busy_ps'],sram_peak_bytes=result['sram_peak_bytes'],
        outstanding_peak=result['outstanding_peak'],mc_peak=result['mc_peak'],
        busiest_links=busiest,task_timelines=timelines,audit=result['audit'])
