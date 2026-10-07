# Pre-layout standard-cell timing: same library, ideal clock and I/O assumptions.
read_liberty $::env(W2W_LIBERTY)
read_verilog $::env(W2W_NETLIST)
link_design $::env(W2W_TOP)
create_clock -name native -period $::env(W2W_PERIOD_NS) [get_ports clk]
set_clock_uncertainty 0.05 [get_clocks native]
set_clock_transition 0.05 [get_clocks native]
set inputs [lsearch -all -inline -not -exact [all_inputs] [lindex [get_ports clk] 0]]
set_input_delay -max 0.2 -clock native $inputs
set_input_delay -min 0 -clock native $inputs
set_driving_cell -lib_cell BUF_X1 $inputs
set_output_delay -max 0.2 -clock native [all_outputs]
set_output_delay -min 0 -clock native [all_outputs]
# Nangate typical liberty uses fF. This is a local-pin load, not an HB model.
set_load 5.0 [all_outputs]
set_false_path -from [get_ports rst]
if {$::env(W2W_TX)} {
    set_false_path -from [get_ports {cfg_shared_direction native_shared_direction}]
}
puts "=== CHECK_SETUP ==="
if {![check_setup -verbose]} {error "Incomplete constraints or timing graph"}
puts "=== UNITS ==="
report_units
# Cell area is reported by Yosys stat with this same Liberty. Standalone OpenSTA
# does not provide OpenROAD's report_design_area command.
puts "=== SETUP ==="
report_worst_slack -max
report_tns
report_checks -path_delay max -group_path_count 5 -format full_clock_expanded -fields {slew cap fanout}
puts "=== HOLD ==="
report_worst_slack -min
report_checks -path_delay min -group_path_count 3 -fields {slew cap fanout}
puts "=== CORE SETUP ==="
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] -group_path_count 1 -fields {slew cap fanout}
puts "=== CORE HOLD ==="
report_checks -path_delay min -from [all_registers -clock_pins] -to [all_registers -data_pins] -group_path_count 1 -fields {slew cap fanout}
puts "=== ELECTRICAL ==="
report_check_types -max_slew -max_capacitance -max_fanout -violators
puts "STA_COMPLETE"
exit
