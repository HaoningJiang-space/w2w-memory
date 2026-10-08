"""Immutable object -> channel/bank/word mapping independent of the return route."""


def words_for_task(task, graph, builder):
    from w2w.domain.protocol import MemoryRequest
    objects = {o.id: o for o in graph.objects}
    sequence = 0
    for access in task.reads:
        obj = objects[access.object_id]
        banks = builder.memories[obj.memory].banks
        start = (obj.offset_bytes+access.offset_bytes)//32
        group = builder.spec.memory_request_bytes//32
        stop = start+access.size_bytes//32
        for word in range(start, stop, group):
            yield MemoryRequest(f'{task.id}/read{sequence}', task.id, task.tile,
                                obj.memory, word % banks, word//banks, min(group, stop-word)*32)
            sequence += 1
