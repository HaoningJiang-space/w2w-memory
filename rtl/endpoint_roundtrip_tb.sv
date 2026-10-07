`timescale 1ns/1ps
module endpoint_roundtrip_tb;
    parameter integer WIDTH=160, DEPTH=2;
    parameter real PERIOD_NS=10.0;
    localparam integer MAX_WORDS=20000, WARMUP=1040, MEASURE=8320;
    reg clk=0, rst=1, cfg_shared_direction=0;
    reg native_valid=0, native_role=0, native_shared_direction=0;
    reg [255:0] native_data=0;
    reg [2:0] sink_ready=0;
    wire ready_a,ready_b;
    wire [2:0] valid_a,valid_b,hv_a,hv_b,hr_a,hr_b;
    wire [767:0] data_a,data_b,hd_a,hd_b;
    wire [11:0] hu_a,hu_b;
`ifdef PPA_NETLIST
    endpoint_ppa_dup duplicated (
`else
    endpoint_star #(.WIDTH(WIDTH),.DEPTH(DEPTH),.CONFIGURABLE(0)) duplicated (
`endif
        .clk(clk),.rst(rst),.cfg_shared_direction(cfg_shared_direction),
        .native_valid(native_valid),.native_role(native_role),
        .native_shared_direction(native_shared_direction),.native_data(native_data),
        .native_ready(ready_a),.sink_ready(sink_ready),.sink_valid(valid_a),.sink_data(data_a),
        .hb_valid(hv_a),.hb_ready(hr_a),.hb_data(hd_a),.hb_units(hu_a));
`ifdef PPA_NETLIST
    endpoint_ppa_cfg configurable (
`else
    endpoint_star #(.WIDTH(WIDTH),.DEPTH(DEPTH),.CONFIGURABLE(1)) configurable (
`endif
        .clk(clk),.rst(rst),.cfg_shared_direction(cfg_shared_direction),
        .native_valid(native_valid),.native_role(native_role),
        .native_shared_direction(native_shared_direction),.native_data(native_data),
        .native_ready(ready_b),.sink_ready(sink_ready),.sink_valid(valid_b),.sink_data(data_b),
        .hb_valid(hv_b),.hb_ready(hr_b),.hb_data(hd_b),.hb_units(hu_b));

    reg [2047:0] words_path, controls_path;
    reg [2047:0] vcd_path;
    reg [255:0] words[0:MAX_WORDS-1];
    integer roles[0:MAX_WORDS-1], expected[0:2][0:MAX_WORDS-1];
    integer wr[0:2],rd[0:2],start_rx[0:2],measure_rx[0:2];
    reg seen[0:MAX_WORDS-1];
    integer fd,control_fd,parsed,role_in,config_value,fault=0;
    reg [255:0] payload;
    integer total=0,accepted=0,received=0,cycle=0,offer,ready_mask,p,d,index;
    integer start_accepted=0,measure_accepted=0,source_stall=0,hb_stall=0,rx_stall=0;
    integer max_pending=0;
    integer quiet_cycles=0,have_vcd=0,dump_start=1040,dump_stop=2080;
    integer power_start_accepted=0,power_start_received=0;
    reg took;
    reg old_native_stall=0,old_native_role,old_native_direction;
    reg [255:0] old_native_data;
    reg [2:0] old_hb_stall=0,old_rx_stall=0;
    reg [767:0] old_hb_data,old_rx_data;
    reg [11:0] old_hb_units;
    initial begin
        if (!$value$plusargs("WORDS=%s",words_path) || !$value$plusargs("CONTROLS=%s",controls_path)
            || !$value$plusargs("DIR=%d",config_value)) $fatal(1,"Missing input");
        if ($value$plusargs("FAULT=%d",fault)) begin end
        have_vcd=$value$plusargs("VCD=%s",vcd_path);
        if(have_vcd) $dumpfile(vcd_path);
        cfg_shared_direction=config_value;
        native_shared_direction=config_value;
        fd=$fopen(words_path,"r");
        control_fd=$fopen(controls_path,"r");
        if (!fd || !control_fd) $fatal(1,"Missing trace file");
        while (!$feof(fd)) begin
            parsed=$fscanf(fd,"%d %h\n",role_in,payload);
            if (parsed==2) begin
                if (total>=MAX_WORDS || role_in<0 || role_in>1) $fatal(1,"Invalid trace");
                words[total]=payload; roles[total]=role_in; seen[total]=0; total=total+1;
            end else if (parsed!=-1) $fatal(1,"Malformed native word");
        end
        $fclose(fd);
        for(p=0;p<3;p=p+1) begin wr[p]=0;rd[p]=0;start_rx[p]=0;measure_rx[p]=0;end
        #(PERIOD_NS/2);clk=1;#(PERIOD_NS/2);clk=0;rst=0;
        while(received<total || quiet_cycles<8) begin
            if(cycle>=120000) $fatal(1,"Drain timeout: accepted=%d received=%d",accepted,received);
            if(have_vcd && cycle==dump_start) begin
                $dumpvars(0,duplicated,configurable);
                power_start_accepted=accepted;power_start_received=received;
            end
            if(have_vcd && cycle==dump_stop) begin
                $dumpoff;
                $display("POWER_WINDOW %0d %0d %0d",dump_stop-dump_start,
                    accepted-power_start_accepted,received-power_start_received);
            end
            if($feof(control_fd)) begin offer=1;ready_mask=7;end
            else begin
                parsed=$fscanf(control_fd,"%d %d\n",offer,ready_mask);
                if(parsed==-1) begin offer=1;ready_mask=7;end
                else if(parsed!=2) $fatal(1,"Malformed cycle controls");
            end
            sink_ready=ready_mask;
            if(!native_valid && accepted<total && offer) begin
                native_valid=1; native_data=words[accepted];native_role=roles[accepted];
            end
            if(fault==1 && cycle==10) cfg_shared_direction=!cfg_shared_direction;
            #(PERIOD_NS*0.4);
            if(cfg_shared_direction!==config_value[0]) $fatal(1,"Static direction changed");
            if(ready_a!==ready_b || valid_a!==valid_b || hv_a!==hv_b || hr_a!==hr_b)
                $fatal(1,"Architectures differ at cycle %0d",cycle);
            if(old_native_stall && (!native_valid || native_data!==old_native_data ||
                 native_role!==old_native_role || native_shared_direction!==old_native_direction))
                $fatal(1,"Native hold violation");
            if(hv_b[2-config_value]) $fatal(1,"Wrong HB destination");
            took=native_valid && ready_a;
            if(took) begin
                d=native_role ? config_value+1 : 0;
                expected[d][wr[d]]=accepted;wr[d]=wr[d]+1;accepted=accepted+1;
            end
            for(p=0;p<3;p=p+1) begin
                if(hv_a[p] && (hd_a[256*p+:256]!==hd_b[256*p+:256] || hu_a[4*p+:4]!==hu_b[4*p+:4]))
                    $fatal(1,"HB payload mismatch");
                if(valid_a[p] && data_a[256*p+:256]!==data_b[256*p+:256]) $fatal(1,"RX pair mismatch");
                if(old_hb_stall[p] && (!hv_a[p] || hd_a[256*p+:256]!==old_hb_data[256*p+:256]
                    || hu_a[4*p+:4]!==old_hb_units[4*p+:4])) $fatal(1,"HB hold violation");
                if(old_rx_stall[p] && (!valid_a[p] || data_a[256*p+:256]!==old_rx_data[256*p+:256]))
                    $fatal(1,"RX hold violation");
                if(valid_a[p] && sink_ready[p]) begin
                    if(rd[p]>=wr[p]) $fatal(1,"Unexpected/wrong-route RX word");
                    index=expected[p][rd[p]];
                    payload=data_a[256*p+:256];
                    if(fault==2 && received==5) payload[127]=!payload[127];
                    if(seen[index] || payload!==words[index]) $fatal(1,"Bit-perfect/tag failure");
                    seen[index]=1;rd[p]=rd[p]+1;received=received+1;
                end
                if(hv_a[p] && !hr_a[p]) hb_stall=hb_stall+1;
                if(valid_a[p] && !sink_ready[p]) rx_stall=rx_stall+1;
            end
            if(native_valid && !ready_a) source_stall=source_stall+1;
            old_native_stall=native_valid && !ready_a;
            old_native_data=native_data;old_native_role=native_role;old_native_direction=native_shared_direction;
            old_hb_stall=hv_a & ~hr_a;old_hb_data=hd_a;old_hb_units=hu_a;
            old_rx_stall=valid_a & ~sink_ready;old_rx_data=data_a;
            clk=1;#(PERIOD_NS*0.1);
`ifndef PPA_NETLIST
            if(256*(accepted-received)!==duplicated.pending_bits ||
               duplicated.pending_bits!==configurable.pending_bits) $fatal(1,"End-to-end bit conservation");
            if(duplicated.pending_bits>max_pending) max_pending=duplicated.pending_bits;
`endif
            if(cycle==WARMUP-1) begin
                start_accepted=accepted;
                for(p=0;p<3;p=p+1) start_rx[p]=rd[p];
            end
            if(cycle==WARMUP+MEASURE-1) begin
                measure_accepted=accepted-start_accepted;
                for(p=0;p<3;p=p+1) measure_rx[p]=rd[p]-start_rx[p];
            end
            if(took) native_valid=0;
            if(received==total) quiet_cycles=quiet_cycles+1;
            #(PERIOD_NS*0.5);clk=0;cycle=cycle+1;
        end
        if(accepted!=total) $fatal(1,"Incomplete drain");
`ifndef PPA_NETLIST
        if(duplicated.pending_bits!=0) $fatal(1,"Nonempty RTL state");
`endif
        for(p=0;p<total;p=p+1) if(!seen[p]) $fatal(1,"Missing tag");
        $display("RESULT %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
            cycle,accepted,rd[0],rd[1],rd[2],measure_rx[0],measure_rx[1],measure_rx[2],
            measure_accepted,source_stall,hb_stall,rx_stall,max_pending);
        $fclose(control_fd);$finish;
    end
endmodule
