"""Verify saved evidence with shared ledgers and independent pair/cost oracles."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from w2w.service.adapters import service_problem
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.synthesis.role_interfaces import catalog


def verify(path):
    raw = Path(path).read_bytes()
    data = json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)
    designs = {d.name: d for d in catalog(contoured_geometry(), data['pairs'])}
    residual = 0.
    pair_error = 0.
    traces = 0
    for row in data['catalog']:
        design = designs[row['id']]
        assert design.layout.sha256 == row['layout_hash']
        assert np.array_equal(design.layout.shares, row['frozen_shares'])
        # Resource checks consume the production ledger, not a second set of rows.
        problem = service_problem(design)
        for replay in row['replays'].values():
            residual = max(residual, problem.audit_rates(replay['served_tb_s']))
        for trace in row['traces']:
            traces += 1
            assert trace['state_repeated'] and trace['conservation_checked_every_slot']
            assert trace['total_per_native'] <= 1 + 1e-12
            assert sum(trace['sent_bits']) == 256 * sum(trace['delivered_words'])
        if row['structure'] == 'k3':
            single = row['replays']['single']['executed_tb_s']
            full = row['replays']['full']['executed_tb_s']
            expected = full + (single-full)*27/35
            pair_error = max(pair_error, abs(expected-row['mean']))
        # Independently count declared physical outputs, including unused roles.
        widths, depths = design.endpoint.widths, design.endpoint.depths
        lanes = sum(widths[p] for ports in design.exposure.mask for p in ports)
        storage = (32*256 if design.endpoint.mode == 'direct'
                   else sum(depths[p]*256 for ports in design.exposure.mask for p in ports))
        assert lanes == row['cost']['export_lane_bits']
        assert storage == row['cost']['endpoint_storage_bits']
        for client in row['population']['clients']:
            assert abs(sum(e['probability'] for e in client['events'])-1) < 1e-12
    assert residual < 1e-8 and pair_error < 1e-12
    return dict(input_sha256=hashlib.sha256(raw).hexdigest(), designs=len(designs),
                periodic_traces=traces, shared_ledger_max_residual=residual,
                independent_pair_max_error=pair_error,
                scope='Shared production resource ledger plus separate pair and integer-count oracles')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('--output')
    args = parser.parse_args()
    result = verify(args.input)
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        Path(args.output).write_text(text)
    print(text)
