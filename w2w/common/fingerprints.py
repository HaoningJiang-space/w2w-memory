"""Historical JSON encodings are distinct; never silently unify their identities."""
from hashlib import sha256
import json


def digest_system_v2(value):
    return sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def digest_read_v1(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
