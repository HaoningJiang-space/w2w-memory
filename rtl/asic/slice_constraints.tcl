# Shared constraints for standalone STA and the matched OpenROAD experiment.
create_clock -name native -period $::env(W2W_PERIOD_NS) [get_ports clk]
set_clock_uncertainty 0.05 [get_clocks native]
set_clock_transition 0.05 [get_clocks native]
set inputs [lsearch -all -inline -not -exact [all_inputs] [lindex [get_ports clk] 0]]
set_input_delay -max 0.2 -clock native $inputs
set_input_delay -min 0 -clock native $inputs
set_driving_cell -lib_cell BUF_X1 $inputs
set_output_delay -max 0.2 -clock native [all_outputs]
set_output_delay -min 0 -clock native [all_outputs]
set_load 5.0 [all_outputs]
set_false_path -from [get_ports rst]
if {$::env(W2W_TX)} {
    # Valid only for the frozen one-partner contract, not dynamic direction STA.
    set_false_path -from [get_ports {cfg_shared_direction native_shared_direction}]
    # Full-width Home emits zero or eight 32-bit units. The runner verifies
    # these three pins are literal zero nets before applying this exception.
    # Tie-cell insertion otherwise makes old check_setup flag static endpoints.
    set_false_path -to [get_ports {home_units[0] home_units[1] home_units[2]}]
}
