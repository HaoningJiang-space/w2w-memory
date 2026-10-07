# Read-only extracted-route audit. Used for the four matched blocks and the
# archived generic Home RX control; does not resize, repair or change the SDC.
set output $::env(W2W_PHYSICAL_OUTPUT)
read_liberty $::env(W2W_LIBERTY)
read_db $output/final.odb
read_sdc $output/final.sdc
read_spef $output/final.spef
set fd [open $output/path_classes.tsv w]
set inputs [lsearch -all -inline -not -exact [all_inputs] [lindex [get_ports clk] 0]]
set outputs [all_outputs]
set launches [all_registers -clock_pins]
set captures [all_registers -data_pins]
foreach name {input_to_reg reg_to_reg reg_to_output input_to_output} \
        from [list $inputs $launches $launches $inputs] \
        to [list $captures $captures $outputs $outputs] {
    foreach mode {max min} {
        set paths [find_timing_paths -path_delay $mode -from $from -to $to \
            -group_count 1 -sort_by_slack]
        if {[llength $paths]} {
            set p [lindex $paths 0]
            puts $fd "$name $mode [get_property $p slack] [get_full_name [get_property $p startpoint]] [get_full_name [get_property $p endpoint]]"
        } else {puts $fd "$name $mode NA"}
    }
}
close $fd
set fd [open $output/cells.csv w]
puts $fd "instance,master,area_um2"
set dbu [[ord::get_db_block] getDbUnitsPerMicron]
foreach inst [[ord::get_db_block] getInsts] {
    set master [$inst getMaster]
    set area [expr {double([$master getWidth])*[$master getHeight]/($dbu*$dbu)}]
    puts $fd "[$inst getName],[$master getName],$area"
}
close $fd
report_parasitic_annotation
puts "PHYSICAL_AUDIT_COMPLETE"
exit
