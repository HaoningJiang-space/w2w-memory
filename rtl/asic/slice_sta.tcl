# Pre-layout standard-cell timing: same library, ideal clock and I/O assumptions.
if {![info exists ::env(W2W_LOADED)]} {
    read_liberty $::env(W2W_LIBERTY)
    read_verilog $::env(W2W_NETLIST)
    link_design $::env(W2W_TOP)
    source [file join $::env(W2W_SCRIPT_DIR) slice_constraints.tcl]
}
set group_flag [expr {[info exists ::env(W2W_LOADED)] ? "-group_count" : "-group_path_count"}]
if {[info exists ::env(W2W_HOLD_REPORT)]} {
    set fd [open $::env(W2W_HOLD_REPORT) w]
    foreach mode {max min} name {setup_ns hold_ns} {
        set path [lindex [find_timing_paths -path_delay $mode $group_flag 1 -sort_by_slack] 0]
        puts $fd "METRIC $name [get_property $path slack]"
    }
    # Preserve every negative hold endpoint, not only the few printed below.
    foreach path [find_timing_paths -path_delay min -slack_max 0 $group_flag 100000] {
        puts $fd "HOLD [get_full_name [get_property $path startpoint]] [get_property $path slack]"
    }
    close $fd
}
puts "=== CHECK_SETUP ==="
set complete [check_setup -verbose > check_setup.rpt]
set fd [open check_setup.rpt]
set checks [read $fd]
close $fd
puts $checks
if {!$complete} {
    # Old OpenSTA reports tied output ports as unconstrained after tie insertion.
    # Permit exactly these three proven literal-zero ports, not arbitrary paths.
    set lines {}
    foreach line [split [string trim $checks] \n] {lappend lines [string trim $line]}
    set expected [list "Warning: There are 3 unconstrained endpoints."         {home_units[0]} {home_units[1]} {home_units[2]}]
    if {![info exists ::env(W2W_LOADED)] || !$::env(W2W_TX) || $lines ne $expected} {
        error "Incomplete constraints or timing graph"
    }
    puts "CONSTANT_ENDPOINTS_ONLY: three literal-zero Home units verified by runner"
}
puts "=== UNITS ==="
report_units
# Cell area is reported by Yosys stat with this same Liberty. Standalone OpenSTA
# does not provide OpenROAD's report_design_area command.
puts "=== SETUP ==="
report_worst_slack -max
report_tns
report_checks -path_delay max $group_flag 5 -format full_clock_expanded -fields {slew capacitance}
puts "=== HOLD ==="
report_worst_slack -min
report_checks -path_delay min $group_flag 3 -fields {slew capacitance}
puts "=== CORE SETUP ==="
report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] $group_flag 1 -fields {slew capacitance}
puts "=== CORE HOLD ==="
report_checks -path_delay min -from [all_registers -clock_pins] -to [all_registers -data_pins] $group_flag 1 -fields {slew capacitance}
puts "=== ELECTRICAL ==="
report_check_types -max_slew -max_capacitance -max_fanout -violators
puts "STA_COMPLETE"
exit
