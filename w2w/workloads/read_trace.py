"""Logical, word-aligned read DAGs, independent of any memory architecture."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')


@dataclass(frozen=True)
class ReadObject:
    id: str
    size_bytes: int
    compute: int


@dataclass(frozen=True)
class ReadSpan:
    object: str
    offset_bytes: int
    size_bytes: int


@dataclass(frozen=True)
class ReadTask:
    id: str
    compute: int | None
    reads: tuple = ()
    dependencies: tuple = ()
    release_slot: int = 0
    compute_slots: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'reads', tuple(self.reads))
        object.__setattr__(self, 'dependencies', tuple(self.dependencies))


@dataclass(frozen=True)
class ReadTrace:
    objects: tuple
    tasks: tuple
    evidence: str
    source: str
    word_bytes: int = 32
    schema: str = 'w2w.read-trace.v1'

    def __post_init__(self):
        object.__setattr__(self, 'objects', tuple(self.objects))
        object.__setattr__(self, 'tasks', tuple(self.tasks))
        if (self.schema != 'w2w.read-trace.v1' or self.evidence not in ('synthetic', 'captured')
                or not isinstance(self.source, str) or not self.source.strip()):
            raise ValueError('Explicit schema, evidence class and source required')
        integer(self.word_bytes, 'word_bytes', 1)
        objects = {o.id: o for o in self.objects}
        tasks = {t.id: t for t in self.tasks}
        if (not tasks or len(tasks) != len(self.tasks) or len(objects) != len(self.objects)
                or any(not isinstance(k, str) or not k for k in (*tasks, *objects))):
            raise ValueError('Nonempty unique string IDs and at least one task required')
        for obj in self.objects:
            integer(obj.size_bytes, 'object size', 1)
            integer(obj.compute, 'object compute')
            if obj.size_bytes % self.word_bytes:
                raise ValueError('Object sizes must be word aligned')
        for task in self.tasks:
            integer(task.release_slot, 'release_slot')
            integer(task.compute_slots, 'compute_slots')
            if task.compute is not None:
                integer(task.compute, 'task compute')
            if (len(set(task.dependencies)) != len(task.dependencies)
                    or any(d not in tasks for d in task.dependencies)):
                raise ValueError('Duplicate or unknown task dependency')
            for read in task.reads:
                if read.object not in objects or objects[read.object].compute != task.compute:
                    raise ValueError('Reads must execute at the object owner compute')
                integer(read.offset_bytes, 'read offset')
                integer(read.size_bytes, 'read size', 1)
                if (read.offset_bytes % self.word_bytes or read.size_bytes % self.word_bytes
                        or read.offset_bytes + read.size_bytes > objects[read.object].size_bytes):
                    raise ValueError('Read must be aligned and inside its logical object')
        # Kahn's algorithm avoids a recursion limit for long decode chains.
        followers = {key: [] for key in tasks}
        degree = {t.id: len(t.dependencies) for t in self.tasks}
        for task in self.tasks:
            for parent in task.dependencies:
                followers[parent].append(task.id)
        ready = [key for key, value in degree.items() if value == 0]
        visited = 0
        while ready:
            visited += 1
            for child in followers[ready.pop()]:
                degree[child] -= 1
                if degree[child] == 0:
                    ready.append(child)
        if visited != len(tasks):
            raise ValueError('Task dependencies contain a cycle')

    def record(self):
        return asdict(self)

    @property
    def sha256(self):
        return digest(self.record())

    @classmethod
    def from_record(cls, row):
        return cls(**{**row, 'objects': tuple(ReadObject(**o) for o in row['objects']),
                      'tasks': tuple(ReadTask(**{**t, 'reads': tuple(ReadSpan(**r)
                                              for r in t.get('reads', ()))}) for t in row['tasks'])})

    def words(self, task):
        """Lazy logical word stream: never expand an entire expert weight tensor."""
        for read in task.reads:
            for word in range(read.offset_bytes // self.word_bytes,
                              (read.offset_bytes + read.size_bytes) // self.word_bytes):
                yield read.object, word


def synthetic_read_suite(compute_xy):
    """Frozen coordinate-based cases; never inspect sharing partners or rates."""
    xs, ys = sorted({v[0] for v in compute_xy}), sorted({v[1] for v in compute_xy})
    grid = {(ys.index(y), xs.index(x)): c for c, (x, y) in enumerate(compute_xy)}
    if len(xs) != 6 or len(ys) != 6 or len(grid) != 36:
        raise ValueError('Registered suite requires a complete 6 by 6 compute grid')
    base = 2496
    objects = tuple(ReadObject(f'object{c:02}', 4 * base * 32, c) for c in range(36))
    group = lambda rows, cols: tuple(grid[r, c] for r in rows for c in cols)
    dispersed = group((0, 2, 4), (0, 2, 4))
    clustered = group(range(3), range(3))
    center = grid[2, 2]
    cases = {
        'single': ((center,),),
        'dispersed9': (dispersed,),
        'clustered9': (clustered,),
        'full36': (tuple(range(36)),),
        'moving9': tuple(group(range(r, r + 3), range(c, c + 3))
                         for r, c in ((0, 0), (0, 3), (3, 0), (3, 3))),
        'straggler9': (dispersed,),
        'short9': (dispersed,),
    }
    suite = {}
    for name, stages in cases.items():
        tasks, previous = [], ()
        for stage, clients in enumerate(stages):
            reads = []
            for c in clients:
                count = 64 if name == 'short9' else base
                if name == 'straggler9' and c == center:
                    count *= 4
                task_id = f's{stage}/c{c:02}'
                reads.append(task_id)
                tasks.append(ReadTask(task_id, c, (ReadSpan(f'object{c:02}', 0, count * 32),),
                                      previous, compute_slots=0 if name == 'short9' else 8))
            join = f's{stage}/join'
            tasks.append(ReadTask(join, None, dependencies=tuple(reads)))
            previous = (join,)
        if name == 'straggler9':
            tasks.append(ReadTask('post_join', center, dependencies=previous, compute_slots=32))
        suite[name] = ReadTrace(objects, tuple(tasks), 'synthetic',
                               f'FINITE_READ_STUDY.md/{name}; coordinate-selected, no partner selection')
    return suite
