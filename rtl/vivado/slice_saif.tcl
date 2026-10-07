# XSim only. Preserve the original testbench scoreboard through final drain.
if {[info exists ::env(W2W_SAIF_FILE)]} {
    set period $::env(W2W_PERIOD_NS)
    run [expr {1041 * $period}] ns
    open_saif $::env(W2W_SAIF_FILE)
    log_saif [get_objects -r /endpoint_roundtrip_tb/duplicated/*]
    log_saif [get_objects -r /endpoint_roundtrip_tb/configurable/*]
    run [expr {1040 * $period}] ns
    close_saif
}
run all
quit
