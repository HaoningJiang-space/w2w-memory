# Four separately implemented local blocks; RX mapping is identical for both TXs.
lassign $argv root out kind part period simdir
file mkdir $out
set_param general.maxThreads 2
# Vivado synthesis defines SYNTHESIS automatically. read_verilog -define would
# require a different compilation-unit mode and is unnecessary here.
read_verilog -sv [list $root/rtl/cse_bank.sv $root/rtl/endpoint_link.sv]
set tx [string match tx_* $kind]
if {$tx} {
    set top endpoint_source
    set generics [list WIDTH=160 DEPTH=2 CONFIGURABLE=[expr {$kind eq "tx_cfg"}]]
} else {
    set top endpoint_rx
    set generics [list WIDTH=[expr {$kind eq "rx_home" ? 256 : 160}]]
}
set xdc [open $out/constraints.xdc w]
puts $xdc "create_clock -name native -period $period \[get_ports clk\]"
puts $xdc {set_clock_uncertainty 0.05 [get_clocks native]}
puts $xdc {set_input_delay -max 0.2 -clock native [remove_from_collection [all_inputs] [get_ports clk]]}
puts $xdc {set_input_delay -min 0 -clock native [remove_from_collection [all_inputs] [get_ports clk]]}
puts $xdc {set_output_delay -max 0.2 -clock native [all_outputs]}
puts $xdc {set_output_delay -min 0 -clock native [all_outputs]}
puts $xdc {set_false_path -from [get_ports rst]}
if {$tx} {
    puts $xdc {set_false_path -from [get_ports -quiet {cfg_shared_direction native_shared_direction}]}
}
close $xdc
read_xdc $out/constraints.xdc
synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt -generic $generics
# OOC clock location supplies a common clock-origin assumption without board I/O.
set clock_site [lindex [lsort [get_sites -filter {SITE_TYPE == BUFGCE}]] 0]
if {$clock_site eq ""} {
    set clock_site [lindex [lsort [get_sites -filter {SITE_TYPE == BUFGCTRL}]] 0]
}
if {$clock_site ne ""} {set_property HD.CLK_SRC $clock_site [get_ports clk]}
report_utilization -hierarchical -file $out/synth_utilization.rpt
opt_design
place_design
route_design
write_checkpoint -force $out/routed.dcp
report_utilization -hierarchical -file $out/utilization.rpt
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file $out/timing.rpt
report_route_status -file $out/route.rpt
set summary [open $out/metrics.tsv w]
puts $summary "kind\t$kind"
puts $summary "part\t$part"
puts $summary "period_ns\t$period"
puts $summary "clock_site\t$clock_site"
foreach mode {max min} {
    set path [get_timing_paths -delay_type $mode -max_paths 1]
    if {[llength $path]} {
        puts $summary "${mode}_slack_ns\t[get_property SLACK $path]"
        puts $summary "${mode}_datapath_ns\t[get_property DATAPATH_DELAY $path]"
    }
}
close $summary
foreach saif [lsort [glob $simdir/*/activity.saif]] {
    set case [file tail [file dirname $saif]]
    if {$kind eq "tx_dup"} {set scopes {duplicated/source}}
    if {$kind eq "tx_cfg"} {set scopes {configurable/source}}
    if {$kind eq "rx_home"} {set scopes {duplicated/home_rx}}
    if {$kind eq "rx_shared"} {set scopes {duplicated/left_rx duplicated/right_rx}}
    foreach scope $scopes {
        set label "${case}_[file tail $scope]"
        reset_switching_activity
        read_saif -strip_path endpoint_roundtrip_tb/$scope -out_file $out/${label}_annotation.rpt $saif
        report_power -file $out/${label}_power.rpt
    }
}
exit
