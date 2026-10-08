"""Immutable object -> channel/bank/word mapping independent of the return route."""


def words_for_task(task, graph, builder):
    from w2w.domain.protocol import MemoryRequest
    objects = {o.id: o for o in graph.objects}
    sequence = 0
    for access in task.reads:
        obj = objects[access.object_id]
        banks = builder.memories[obj.memory].banks
        start = (obj.offset_bytes+access.offset_bytes)//32
        for word in range(start, start+access.size_bytes//32):
            yield MemoryRequest(f'{task.id}/read{sequence}', task.id, task.tile,
                                obj.memory, word % banks, word//banks)
            sequence += 1
