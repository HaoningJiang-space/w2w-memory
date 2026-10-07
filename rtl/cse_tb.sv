`timescale 1ns/1ps
module cse_tb;
    parameter integer SHARED_WIDTH = 160;
    parameter integer SHARED_DEPTH = 2;
    parameter integer MODE = 2;
    reg clk=0, rst=1, direction=0, in_valid=0;
    reg [1:0] in_dest=0;
    reg [255:0] in_data=0;
    reg [2:0] out_ready=0;
    wire in_ready;
    wire [255:0] home_data;
    wire [SHARED_WIDTH-1:0] left_data, right_data;
    wire [3:0] home_units, left_units, right_units;
`ifdef GATE
    cse_bank dut (.*);
`else
    cse_bank #(.SHARED_WIDTH(SHARED_WIDTH), .SHARED_DEPTH(SHARED_DEPTH), .MODE(MODE)) dut (.*);
`endif
    reg [2047:0] stimulus;
    integer fd, parsed, cycle=0, cfg, expected_ready, h_count, l_count, r_count;
    reg [255:0] h_data, l_data, r_data;
    reg [255:0] h_mask, l_mask, r_mask;
    initial begin
        if (!$value$plusargs("STIM=%s", stimulus)) $fatal(1,"Missing stimulus");
        if (!$value$plusargs("DIR=%d", cfg)) $fatal(1,"Missing direction");
        direction = cfg;
        fd=$fopen(stimulus,"r");
        if (!fd) $fatal(1,"Cannot open stimulus");
        #5; clk=1; #5; clk=0; rst=0;
        while (!$feof(fd)) begin
            parsed=$fscanf(fd,"%d %d %h %b %d %d %h %d %h %d %h\n",
                in_valid,in_dest,in_data,out_ready,expected_ready,
                h_count,h_data,l_count,l_data,r_count,r_data);
            if (parsed != 11) $fatal(1,"Malformed vector at %0d",cycle);
            #5;
            h_mask = h_count == 8 ? {256{1'b1}} : ((256'b1 << (32*h_count))-1);
            l_mask = (256'b1 << (32*l_count))-1;
            r_mask = (256'b1 << (32*r_count))-1;
            if (in_ready !== expected_ready[0] || home_units !== h_count[3:0] ||
                left_units !== l_count[3:0] || right_units !== r_count[3:0] ||
                (home_data & h_mask) !== h_data ||
                ({{(256-SHARED_WIDTH){1'b0}},left_data} & l_mask) !== l_data ||
                ({{(256-SHARED_WIDTH){1'b0}},right_data} & r_mask) !== r_data)
                $fatal(1,"Mismatch cycle=%0d ready=%b/%d units=%d,%d,%d expected=%d,%d,%d",
                    cycle,in_ready,expected_ready,home_units,left_units,right_units,h_count,l_count,r_count);
            clk=1; #5; clk=0; cycle=cycle+1;
        end
        $fclose(fd);
        $display("PASS %0d cycles",cycle);
        $finish;
    end
endmodule
