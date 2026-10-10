"""Current Architecture V3 entrypoints; historical commands use frozen tags."""
COMMANDS = {
    'compile_machine': 'w2w.experiments.compile_machine',
    'run_vertical_access': 'w2w.experiments.run_vertical_access',
    'analyze_vertical_access': 'w2w.analysis.vertical_access',
    'run_gateway_baseline': 'w2w.experiments.run_gateway_baseline',
    'run_memory_hierarchy': 'w2w.experiments.run_memory_hierarchy',
}
COMMAND_STATUS = {name:'current' for name in COMMANDS}
COMMAND_SCOPES = {
    'compile_machine':'physical_architecture_v3',
    'run_vertical_access':'one_routed_ffn_layer_v3',
    'analyze_vertical_access':'completed_architecture_v3_evidence',
    'run_gateway_baseline':'finite_ready_aware_central_baseline',
    'run_memory_hierarchy':'finite_distributed_sram_two_layer_proxy',
}
