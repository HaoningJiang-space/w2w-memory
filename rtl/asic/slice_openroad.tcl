# Local signal/clock P&R only. No wafer wires, HB extraction or power analysis.
set here $::env(W2W_SCRIPT_DIR)
set platform $::env(W2W_PLATFORM)
set output $::env(W2W_PHYSICAL_OUTPUT)
set_thread_count 2
read_lef $platform/lef/NangateOpenCellLibrary.tech.lef
read_lef $platform/lef/NangateOpenCellLibrary.macro.mod.lef
read_liberty $::env(W2W_LIBERTY)
read_verilog $::env(W2W_NETLIST)
link_design $::env(W2W_TOP)
source $here/slice_constraints.tcl
initialize_floorplan -utilization 30 -aspect_ratio 1 -core_space 5 \
    -site FreePDK45_38x28_10R_NP_162NW_34O
source $platform/make_tracks.tcl
source $platform/setRC.tcl
set ::env(TAP_CELL_NAME) TAPCELL_X1
source $platform/tapcell.tcl
set ::env(MIN_ROUTING_LAYER) metal2
set ::env(MIN_CLK_ROUTING_LAYER) metal4
set ::env(MAX_ROUTING_LAYER) metal10
source $platform/fastroute.tcl
insert_tiecells LOGIC0_X1/Z
insert_tiecells LOGIC1_X1/Z
place_pins -hor_layers metal5 -ver_layers metal6 -random -random_seed 42

set metrics [open $output/stages.csv w]
puts $metrics "stage,cell_area_um2,hold_buffers,hold_buffer_area_um2,setup_ns,hold_ns"
proc snapshot {name} {
    global metrics
    set block [ord::get_db_block]
    set dbu [$block getDbUnitsPerMicron]
    set area 0.0
    set hold_area 0.0
    set hold_count 0
    foreach inst [$block getInsts] {
        set master [$inst getMaster]
        set a [expr {double([$master getWidth])*[$master getHeight]/($dbu*$dbu)}]
        set area [expr {$area+$a}]
        if {[string match hold* [$inst getName]]} {
            incr hold_count
            set hold_area [expr {$hold_area+$a}]
        }
    }
    set setup [get_property [lindex [find_timing_paths -path_delay max -group_count 1 -sort_by_slack] 0] slack]
    set hold [get_property [lindex [find_timing_paths -path_delay min -group_count 1 -sort_by_slack] 0] slack]
    puts $metrics "$name,$area,$hold_count,$hold_area,$setup,$hold"
    flush $metrics
    return [list $setup $hold]
}
snapshot imported
global_placement -density 0.40
detailed_placement
estimate_parasitics -placement
repair_design
detailed_placement
clock_tree_synthesis -buf_list {CLKBUF_X1 CLKBUF_X2 CLKBUF_X3} -root_buf CLKBUF_X3 \
    -sink_clustering_enable
set_propagated_clock [all_clocks]
detailed_placement
estimate_parasitics -placement
snapshot post_cts_before_repair
repair_timing -setup
repair_timing -hold -hold_margin 0.02 -max_buffer_percent 50
detailed_placement
check_placement -verbose
snapshot post_cts_repaired
global_route -guide_file $output/route.guide -congestion_iterations 50
estimate_parasitics -global_routing
repair_design
repair_timing -setup
repair_timing -hold -hold_margin 0.02 -max_buffer_percent 50
detailed_placement
global_route -guide_file $output/route.guide -congestion_iterations 50
estimate_parasitics -global_routing
snapshot global_route_repaired
detailed_route -output_drc $output/route_drc.rpt -output_maze $output/maze.log \
    -bottom_routing_layer metal2 -top_routing_layer metal10 -or_seed 42
define_process_corner -ext_model_index 0 typical
extract_parasitics -ext_model_file $platform/rcx_patterns.rules
snapshot post_route_extracted
close $metrics
write_spef $output/final.spef
write_def $output/final.def
write_db $output/final.odb
write_verilog -remove_cells {TAPCELL_X1} $output/netlist.v
write_sdc $output/final.sdc
set ::env(W2W_LOADED) 1
puts "PHYSICAL_FLOW_COMPLETE"
source $here/slice_sta.tcl
