"""Current Architecture V3 entrypoints; historical commands use frozen tags."""
COMMANDS = {
    'compile_machine': 'w2w.experiments.compile_machine',
    'run_vertical_access': 'w2w.experiments.run_vertical_access',
    'analyze_vertical_access': 'w2w.analysis.vertical_access',
    'run_gateway_baseline': 'w2w.experiments.run_gateway_baseline',
    'run_memory_hierarchy': 'w2w.experiments.run_memory_hierarchy',
    'run_operand_access': 'w2w.experiments.run_operand_access',
    'analyze_operand_access': 'w2w.analysis.operand_access',
}
COMMAND_STATUS = {name:'current' for name in COMMANDS}
COMMAND_SCOPES = {
    'compile_machine':'physical_architecture_v3',
    'run_vertical_access':'one_routed_ffn_layer_v3',
    'analyze_vertical_access':'completed_architecture_v3_evidence',
    'run_gateway_baseline':'finite_ready_aware_central_baseline',
    'run_memory_hierarchy':'finite_distributed_sram_two_layer_proxy',
    'run_operand_access':'cold_ffn_with_contiguous_operands_and_control',
    'analyze_operand_access':'audited_contiguous_operand_access_pair',
}
