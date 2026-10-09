"""Named candidate recipes are validated, not silently ignored configuration."""
import json
from pathlib import Path
from .vertical_memory import vertical_memory


def from_recipe(path,organization):
    record=json.loads(Path(path).read_text())
    if record['schema']!='w2w.machine-recipe.v3' or record['preset']!='distributed_compute_vertical_memory':
        raise ValueError('Unknown machine recipe')
    fixed=dict(clusters_per_reticle=4,pes_per_cluster=4096,sram_bytes_per_pe=49152,
        macs_per_pe_cycle=4,compute_period_ps=1000,native_domains_per_region=32,
        domain_capacity_bytes=67108864,domain_data_bits=128,native_period_ps=3760,
        fabric_cut_data_bits=1024,fabric_cut_control_bits=1024,fabric_input_buffer_bytes=32768)
    required={'schema','preset','reticle_rows','reticle_columns',*fixed}
    if not required<=record.keys() or record.keys()-required-{'source'}:
        raise ValueError('Machine recipe has missing or unknown fields')
    if 'source' in record and (not isinstance(record['source'],str) or not record['source']):
        raise ValueError('source is non-executable provenance text')
    if any(record.get(k)!=v for k,v in fixed.items()):
        raise ValueError('This named preset has fixed explicit service ratios; define a new preset for another ratio')
    return vertical_memory(organization,rows=record['reticle_rows'],columns=record['reticle_columns'])
