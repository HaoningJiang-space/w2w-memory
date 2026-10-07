# Pre-layout standard-cell timing: same library, ideal clock and I/O assumptions.
if {![info exists ::env(W2W_LOADED)]} {
    read_liberty $::env(W2W_LIBERTY)
    read_verilog $::env(W2W_NETLIST)
    link_design $::env(W2W_TOP)
    source [file join [file dirname [info script]] slice_constraints.tcl]
}
if {[info exists ::env(W2W_HOLD_REPORT)]} {
    set fd [open $::env(W2W_HOLD_REPORT) w]
    foreach mode {max min} name {setup_ns hold_ns} {
        set path [lindex [find_timing_paths -path_delay $mode -group_path_count 1 -sort_by_slack] 0]
        puts $fd "METRIC $name [get_property $path slack]"
    }
    # Preserve every negative hold endpoint, not only the few printed below.
    foreach path [find_timing_paths -path_delay min -slack_max 0 -group_path_count 100000] {
        puts $fd "HOLD [get_full_name [get_property $path startpoint]] [get_property $path slack]"
    }
    close $fd
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
