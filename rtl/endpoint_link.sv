`timescale 1ns/1ps
// Read-return only. Native role/direction come from frozen address mapping.
// Source machinery precedes every HB edge; receivers never forward data.
// Reuse the archived whole-word FIFO/packetizer with a counted elastic beat.
module endpoint_tx #(
    parameter integer WIDTH=160, DEPTH=2
) (
    input wire clk, rst, native_valid,
    input wire [255:0] native_data,
    output wire native_ready,
    output reg beat_valid,
    input wire beat_ready,
    output reg [WIDTH-1:0] beat_data,
    output reg [3:0] beat_units
);
    wire pop;
    wire [255:0] head, next_word;
    wire [1:0] words;
    wire [WIDTH-1:0] data;
    wire [3:0] units;
    wire advance = !beat_valid || beat_ready;
    cse_fifo #(.DEPTH(DEPTH)) fifo (
        .clk(clk), .rst(rst), .valid(native_valid && !rst), .data(native_data),
        .ready(native_ready), .pop(pop), .head_view(head),
        .next_view(next_word), .view_count(words));
    cse_packetizer #(.WIDTH(WIDTH)) gearbox (
        .clk(clk), .rst(rst), .active(!rst), .ready(advance),
        .head_view(head), .next_view(next_word), .view_count(words),
        .pop(pop), .data(data), .units(units));
    always @(posedge clk) begin
        if (rst) begin
            beat_valid <= 0;
            beat_data <= 0;
            beat_units <= 0;
        end else if (advance) begin
            beat_valid <= units != 0;
            beat_units <= units;
            if (units != 0) beat_data <= data;
        end
    end
`ifndef SYNTHESIS
    wire [31:0] pending_bits;
    if (WIDTH == 256) begin: monitor_full
        assign pending_bits = fifo.count*256 + (beat_valid ? beat_units*32 : 0);
    end else begin: monitor_narrow
        assign pending_bits = fifo.count*256 - gearbox.serial_word.offset*32
                              + (beat_valid ? beat_units*32 : 0);
    end
    always @(posedge clk) if (!rst && fifo.count > DEPTH) $fatal(1,"TX FIFO bound");
`endif
endmodule

module endpoint_rx #(parameter integer WIDTH=160) (
    input wire clk, rst, beat_valid,
    output wire beat_ready,
    input wire [WIDTH-1:0] beat_data,
    input wire [3:0] beat_units,
    output wire word_valid,
    input wire word_ready,
    output wire [255:0] word_data
);
    function automatic integer gcd(input integer a,b);
        integer t;
        begin while (b != 0) begin t=a%b; a=b; b=t; end gcd=a; end
    endfunction
    // TX emits multiples of gcd(256,WIDTH); includes the stalled complete word.
    localparam integer QUANTUM=gcd(256,WIDTH)/32;
    localparam integer CAP_UNITS=(256+WIDTH-gcd(256,WIDTH))/32;
    localparam integer COUNT_BITS=$clog2(CAP_UNITS+1);
    reg [32*CAP_UNITS-1:0] reservoir, updated;
    reg [COUNT_BITS-1:0] count;
    integer n, i;
    wire pop=word_valid && word_ready;
    wire push=beat_valid && beat_ready;
    assign word_valid=count>=8 && !rst;
    assign word_data=reservoir[255:0];
    // Reserve a full beat; readiness does not depend on beat_valid or units.
    assign beat_ready=!rst && count-(pop ? 8 : 0)+WIDTH/32<=CAP_UNITS;
    always @* begin
        updated=pop ? reservoir>>256 : reservoir;
        n=count-(pop ? 8 : 0);
        if (push) begin
            for (i=0; i<WIDTH/32; i=i+1)
                if (i<beat_units) updated[32*(n+i)+:32]=beat_data[32*i+:32];
            n=n+beat_units;
        end
    end
    always @(posedge clk) begin
        if (rst) begin reservoir<=0; count<=0; end
        else begin reservoir<=updated; count<=n; end
    end
`ifndef SYNTHESIS
    wire [31:0] pending_bits=count*32;
    always @(posedge clk) if (!rst) begin
        if (count>CAP_UNITS) $fatal(1,"RX reservoir bound");
        if (push && (beat_units==0 || beat_units>WIDTH/32 || beat_units%QUANTUM!=0))
            $fatal(1,"RX invalid beat units");
    end
`endif
endmodule

module endpoint_source #(
    parameter integer WIDTH=160, DEPTH=2, CONFIGURABLE=1
) (
    input wire clk, rst, cfg_shared_direction,
    input wire native_valid, native_role, native_shared_direction,
    input wire [255:0] native_data,
    output wire native_ready,
    output wire [2:0] hb_valid,
    input wire [2:0] hb_ready,
    output wire [255:0] home_data,
    output wire [WIDTH-1:0] left_data, right_data,
    output wire [3:0] home_units, left_units, right_units
);
    wire home_ready;
    endpoint_tx #(.WIDTH(256),.DEPTH(1)) home (
        .clk(clk),.rst(rst),.native_valid(native_valid && !native_role),
        .native_data(native_data),.native_ready(home_ready),
        .beat_valid(hb_valid[0]),.beat_ready(hb_ready[0]),
        .beat_data(home_data),.beat_units(home_units));
    generate if (CONFIGURABLE) begin: pooled
        wire shared_ready, valid;
        wire [WIDTH-1:0] data;
        wire [3:0] units;
        wire legal=native_shared_direction==cfg_shared_direction;
        assign native_ready=!rst && (native_role ? legal && shared_ready : home_ready);
        endpoint_tx #(.WIDTH(WIDTH),.DEPTH(DEPTH)) shared (
            .clk(clk),.rst(rst),.native_valid(native_valid && native_role && legal),
            .native_data(native_data),.native_ready(shared_ready),
            .beat_valid(valid),.beat_ready(cfg_shared_direction ? hb_ready[2] : hb_ready[1]),
            .beat_data(data),.beat_units(units));
        assign hb_valid[2:1]=cfg_shared_direction ? {valid,1'b0} : {1'b0,valid};
        assign left_data=cfg_shared_direction ? {WIDTH{1'b0}} : data;
        assign right_data=cfg_shared_direction ? data : {WIDTH{1'b0}};
        assign left_units=cfg_shared_direction ? 4'b0 : units;
        assign right_units=cfg_shared_direction ? units : 4'b0;
    end else begin: duplicated
        wire left_ready, right_ready;
        assign native_ready=!rst && (native_role ?
            (native_shared_direction ? right_ready : left_ready) : home_ready);
        endpoint_tx #(.WIDTH(WIDTH),.DEPTH(DEPTH)) left (
            .clk(clk),.rst(rst),.native_valid(native_valid && native_role && !native_shared_direction),
            .native_data(native_data),.native_ready(left_ready),.beat_valid(hb_valid[1]),
            .beat_ready(hb_ready[1]),.beat_data(left_data),.beat_units(left_units));
        endpoint_tx #(.WIDTH(WIDTH),.DEPTH(DEPTH)) right (
            .clk(clk),.rst(rst),.native_valid(native_valid && native_role && native_shared_direction),
            .native_data(native_data),.native_ready(right_ready),.beat_valid(hb_valid[2]),
            .beat_ready(hb_ready[2]),.beat_data(right_data),.beat_units(right_units));
    end endgenerate
`ifndef SYNTHESIS
    wire [31:0] pending_bits;
    if (CONFIGURABLE) assign pending_bits=home.pending_bits+pooled.shared.pending_bits;
    else assign pending_bits=home.pending_bits+duplicated.left.pending_bits+duplicated.right.pending_bits;
`endif
endmodule

// Minimal physical star: three separate direct HB streams and three receivers.
// No C-to-C wire. This is a functional zero-link-delay model, not a timing model.
module endpoint_star #(
    parameter integer WIDTH=160, DEPTH=2, CONFIGURABLE=1
) (
    input wire clk, rst, cfg_shared_direction,
    input wire native_valid, native_role, native_shared_direction,
    input wire [255:0] native_data,
    output wire native_ready,
    input wire [2:0] sink_ready,
    output wire [2:0] sink_valid,
    output wire [767:0] sink_data,
    output wire [2:0] hb_valid, hb_ready,
    output wire [767:0] hb_data,
    output wire [11:0] hb_units
);
    wire [255:0] hd;
    wire [WIDTH-1:0] ld, rd;
    endpoint_source #(.WIDTH(WIDTH),.DEPTH(DEPTH),.CONFIGURABLE(CONFIGURABLE)) source (
        .clk(clk),.rst(rst),.cfg_shared_direction(cfg_shared_direction),
        .native_valid(native_valid),.native_role(native_role),
        .native_shared_direction(native_shared_direction),.native_data(native_data),
        .native_ready(native_ready),.hb_valid(hb_valid),.hb_ready(hb_ready),
        .home_data(hd),.left_data(ld),.right_data(rd),
        .home_units(hb_units[3:0]),.left_units(hb_units[7:4]),.right_units(hb_units[11:8]));
    assign hb_data={{{(256-WIDTH){1'b0}},rd},{{(256-WIDTH){1'b0}},ld},hd};
    endpoint_rx #(.WIDTH(256)) home_rx (.clk(clk),.rst(rst),
        .beat_valid(hb_valid[0]),.beat_ready(hb_ready[0]),.beat_data(hd),.beat_units(hb_units[3:0]),
        .word_valid(sink_valid[0]),.word_ready(sink_ready[0]),.word_data(sink_data[255:0]));
    endpoint_rx #(.WIDTH(WIDTH)) left_rx (.clk(clk),.rst(rst),
        .beat_valid(hb_valid[1]),.beat_ready(hb_ready[1]),.beat_data(ld),.beat_units(hb_units[7:4]),
        .word_valid(sink_valid[1]),.word_ready(sink_ready[1]),.word_data(sink_data[511:256]));
    endpoint_rx #(.WIDTH(WIDTH)) right_rx (.clk(clk),.rst(rst),
        .beat_valid(hb_valid[2]),.beat_ready(hb_ready[2]),.beat_data(rd),.beat_units(hb_units[11:8]),
        .word_valid(sink_valid[2]),.word_ready(sink_ready[2]),.word_data(sink_data[767:512]));
`ifndef SYNTHESIS
    wire [31:0] pending_bits=source.pending_bits+home_rx.pending_bits+left_rx.pending_bits+right_rx.pending_bits;
`endif
endmodule
