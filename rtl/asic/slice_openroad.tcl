# Local signal/clock P&R only. No wafer wires, HB extraction or power analysis.
set here $::env(W2W_SCRIPT_DIR)
set platform $::env(W2W_PLATFORM)
set output $::env(W2W_PHYSICAL_OUTPUT)
set cap_margin 0
if {[info exists ::env(W2W_CAP_MARGIN)]} {set cap_margin $::env(W2W_CAP_MARGIN)}
set limit 50
if {[info exists ::env(W2W_HOLD_BUFFER_PERCENT)]} {set limit $::env(W2W_HOLD_BUFFER_PERCENT)}
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
# A small elastic RX can need more delay cells than its initial logic count.
# If the per-call effort ceiling is reached, keep the inserted cells, legalize,
# refresh RC, and allow at most two further automatic repair passes.
proc repair_hold {model} {
    global limit output
    for {set pass 0} {$pass<3} {incr pass} {
        if {![catch {repair_timing -hold -hold_margin 0.05 -max_buffer_percent $limit} message]} {return}
        if {($message ne "RSZ-0060" && ![string match {*Max buffer count reached*} $message]) || $pass==2} {error $message}
        puts "HOLD_LIMIT_CONTINUE: completed pass [expr {$pass+1}], legalize and refresh $model RC"
        detailed_placement
        if {$model eq "global_routing"} {
            global_route -guide_file $output/route.guide -congestion_iterations 50
        }
        estimate_parasitics -$model
    }
}
snapshot imported
global_placement -density 0.40
detailed_placement
estimate_parasitics -placement
repair_design -cap_margin $cap_margin
detailed_placement
clock_tree_synthesis -buf_list {CLKBUF_X1 CLKBUF_X2 CLKBUF_X3} -root_buf CLKBUF_X3 \
    -sink_clustering_enable
set_propagated_clock [all_clocks]
detailed_placement
estimate_parasitics -placement
snapshot post_cts_before_repair
repair_timing -setup
repair_hold placement
detailed_placement
check_placement -verbose
snapshot post_cts_repaired
global_route -guide_file $output/route.guide -congestion_iterations 50
estimate_parasitics -global_routing
repair_design -cap_margin $cap_margin
repair_timing -setup
repair_hold global_routing
detailed_placement
global_route -guide_file $output/route.guide -congestion_iterations 50
estimate_parasitics -global_routing
snapshot global_route_repaired
detailed_route -output_drc $output/route_drc.rpt -output_maze $output/maze.log \
    -bottom_routing_layer metal2 -top_routing_layer metal10 -or_seed 42
define_process_corner -ext_model_index 0 typical
extract_parasitics -ext_model_file $platform/rcx_patterns.rules
write_spef $output/final.spef
# OpenRCX populates the physical database; explicitly load its SPEF into STA.
read_spef $output/final.spef
report_parasitic_annotation -report_unannotated > $output/parasitic_annotation.rpt
set fd [open $output/parasitic_annotation.rpt]
set annotation [read $fd]
close $fd
if {![regexp {Found 0 partially unannotated drivers\.} $annotation]} {
    error "Incomplete partial parasitic annotation"
}
set unused 0
foreach line [split $annotation \n] {
    if {[regexp {^ ([^ ]+)$} $line -> name]} {
        set pin [get_pins -quiet $name]
        if {[llength $pin]==0} {set pin [get_ports -quiet $name]}
        if {[llength $pin]!=1} {error "Cannot resolve unannotated pin $name"}
        # get_fanout includes the root itself in this pinned OpenSTA version.
        foreach sink [get_fanout -from $pin -flat -pin_levels 1] {
            if {[get_full_name $sink] ne $name} {error "Loaded net missing RC: $name"}
        }
        incr unused
    }
}
puts "PARASITIC_ANNOTATION_COMPLETE: $unused unused drivers; no loaded net missing RC"
snapshot post_route_extracted
close $metrics
write_def $output/final.def
write_db $output/final.odb
write_verilog -remove_cells {TAPCELL_X1} $output/netlist.v
write_sdc $output/final.sdc
set ::env(W2W_LOADED) 1
puts "PHYSICAL_FLOW_COMPLETE"
source $here/slice_sta.tcl
