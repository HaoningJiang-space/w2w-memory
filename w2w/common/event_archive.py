"""Lossless column storage for complete physical events, not event omission.

Decode restores every key/value and original event order. A canonical decoded
SHA256 binds the full system record; archive SHA256 separately binds file bytes.
This affects archival storage only, never execution or Native callbacks.
"""
import base64,gzip,hashlib,json
from collections import defaultdict
from pathlib import Path


def canonical_sha(value):
    h=hashlib.sha256()
    for part in json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False).iterencode(value):h.update(part.encode())
    return h.hexdigest()


def _integers(values):
    output=bytearray();last=0
    for value in values:
        delta=value-last;last=value;n=2*delta if delta>=0 else -2*delta-1
        while n>=128:output.append((n&127)|128);n>>=7
        output.append(n)
    return base64.b64encode(output).decode()


def _read_integers(text,count):
    data=base64.b64decode(text,validate=True);result=[];n=shift=last=0
    for b in data:
        n|=(b&127)<<shift
        if b&128:shift+=7;continue
        delta=n//2 if n%2==0 else -(n//2)-1;last+=delta;result.append(last);n=shift=0
    if shift or len(result)!=count:raise ValueError('Truncated or excess event archive integers')
    return result


def encode(record):
    if 'events_codec' in record or 'events' not in record:raise ValueError('Unencoded full event record required')
    groups=defaultdict(list);order=[];kinds=[];ids={};strings=[];string_ids={}
    def string(s):
        if s not in string_ids:string_ids[s]=len(strings);strings.append(s)
        return string_ids[s]
    for event in record['events']:
        kind=event['kind']
        if kind not in ids:ids[kind]=len(kinds);kinds.append(kind)
        groups[kind].append(event);order.append(ids[kind])
    columns=[]
    for kind in kinds:
        rows=groups[kind];fields={}
        for field in sorted(set().union(*(e.keys() for e in rows))-{'kind'}):
            present=[i for i,e in enumerate(rows) if field in e];values=[rows[i][field] for i in present]
            if all(type(v) is int for v in values):c=dict(encoding='delta-integers',values=_integers(values))
            elif all(type(v) is str for v in values):c=dict(encoding='strings',values=_integers([string(v) for v in values]))
            else:c=dict(encoding='json',values=values)
            c['count']=len(values)
            if len(present)!=len(rows):c['present']=_integers(present)
            fields[field]=c
        columns.append(dict(kind=kind,count=len(rows),fields=fields))
    out={k:v for k,v in record.items() if k!='events'}
    out['events_codec']=dict(schema='w2w.lossless-event-columns.v1',count=len(order),order=_integers(order),
        strings=strings,columns=columns,decoded_sha256=canonical_sha(record))
    return out


def decode(record):
    if 'events_codec' not in record:return record
    c=record['events_codec']
    if c['schema']!='w2w.lossless-event-columns.v1' or 'events' in record:raise ValueError('Invalid event archive schema')
    groups=[]
    for column in c['columns']:
        rows=[dict(kind=column['kind']) for _ in range(column['count'])]
        if 'kind' in column['fields'] or 'time_ps' not in column['fields']:raise ValueError('Invalid physical event fields')
        for field,values in column['fields'].items():
            n=values['count'];present=_read_integers(values['present'],n) if 'present' in values else list(range(len(rows)))
            if n!=len(present) or present!=sorted(set(present)) or any(i<0 or i>=len(rows) for i in present):raise ValueError('Invalid field presence/order')
            if values['encoding'] in ('delta-integers','strings'):
                data=_read_integers(values['values'],n)
                if values['encoding']=='strings':
                    if any(i<0 or i>=len(c['strings']) for i in data):raise ValueError('Invalid string association')
                    data=[c['strings'][i] for i in data]
            elif values['encoding']=='json':
                data=values['values']
                if len(data)!=n:raise ValueError('Invalid JSON field size')
            else:raise ValueError('Unknown archive field encoding')
            for i,v in zip(present,data):rows[i][field]=v
        groups.append(rows)
    cursor=[0]*len(groups);events=[]
    for k in _read_integers(c['order'],c['count']):
        if not 0<=k<len(groups) or cursor[k]>=len(groups[k]):raise ValueError('Invalid event ordering')
        events.append(groups[k][cursor[k]]);cursor[k]+=1
    if any(cursor[i]!=len(rows) for i,rows in enumerate(groups)):raise ValueError('Omitted physical events')
    out={k:v for k,v in record.items() if k!='events_codec'};out['events']=events
    if canonical_sha(out)!=c['decoded_sha256']:raise ValueError('Decoded physical record SHA256 differs')
    return out


def write_execution(path,record):
    stored=encode(record)
    with gzip.open(path,'wt',compresslevel=6) as f:json.dump(stored,f,separators=(',',':'),allow_nan=False)
    return stored['events_codec']['decoded_sha256']


def read_execution(path):
    with gzip.open(Path(path),'rt') as f:return decode(json.load(f))
