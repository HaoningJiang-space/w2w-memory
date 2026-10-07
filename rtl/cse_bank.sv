// One native 256-bit admission before output drain per slot. Queue depth
// includes the transmitting word. No same-slot re-admission after a pop.
// Direction is a reticle configuration input, held constant between resets.
// MODE 0: independent FIFO + packetizer per shared direction.
// MODE 1: common FIFO, independent packetizers, wide view direction select.
// MODE 2: common FIFO + packetizer, narrow beat direction select.
module cse_bank #(
    parameter integer SHARED_WIDTH = 160,
    parameter integer SHARED_DEPTH = 2,
    parameter integer MODE = 2
) (
    input wire clk, rst, direction,
    input wire in_valid,
    input wire [1:0] in_dest, // 0 home, 1 direction-left, 2 direction-right
    input wire [255:0] in_data,
    output wire in_ready,
    input wire [2:0] out_ready,
    output wire [255:0] home_data,
    output wire [SHARED_WIDTH-1:0] left_data, right_data,
    output wire [3:0] home_units, left_units, right_units
);
    wire hr, hp;
    wire [255:0] hh, ht;
    wire [1:0] hn;
    cse_fifo #(.DEPTH(1)) home_fifo (
        .clk(clk), .rst(rst), .valid(in_valid && in_dest == 0),
        .data(in_data), .ready(hr), .pop(hp),
        .head_view(hh), .next_view(ht), .view_count(hn));
    cse_packetizer #(.WIDTH(256)) home_sender (
        .clk(clk), .rst(rst), .active(1'b1), .ready(out_ready[0]),
        .head_view(hh), .next_view(ht), .view_count(hn),
        .pop(hp), .data(home_data), .units(home_units));

    generate if (MODE == 0) begin: independent
        wire lr, rr, lp, rp;
        wire [255:0] lh, lt, rh, rt;
        wire [1:0] ln, rn;
        assign in_ready = in_dest == 0 ? hr : (in_dest == 1 ? lr : (in_dest == 2 ? rr : 1'b0));
        cse_fifo #(.DEPTH(SHARED_DEPTH)) left_fifo (
            .clk(clk), .rst(rst), .valid(in_valid && in_dest == 1), .data(in_data),
            .ready(lr), .pop(lp), .head_view(lh), .next_view(lt), .view_count(ln));
        cse_fifo #(.DEPTH(SHARED_DEPTH)) right_fifo (
            .clk(clk), .rst(rst), .valid(in_valid && in_dest == 2), .data(in_data),
            .ready(rr), .pop(rp), .head_view(rh), .next_view(rt), .view_count(rn));
        cse_packetizer #(.WIDTH(SHARED_WIDTH)) left_sender (
            .clk(clk), .rst(rst), .active(1'b1), .ready(out_ready[1]),
            .head_view(lh), .next_view(lt), .view_count(ln), .pop(lp), .data(left_data), .units(left_units));
        cse_packetizer #(.WIDTH(SHARED_WIDTH)) right_sender (
            .clk(clk), .rst(rst), .active(1'b1), .ready(out_ready[2]),
            .head_view(rh), .next_view(rt), .view_count(rn), .pop(rp), .data(right_data), .units(right_units));
    end else begin: configurable
        wire sr, sp;
        wire [255:0] sh, st;
        wire [1:0] sn;
        wire legal_shared = in_dest == (direction ? 2 : 1);
        assign in_ready = in_dest == 0 ? hr : (legal_shared ? sr : 1'b0);
        cse_fifo #(.DEPTH(SHARED_DEPTH)) shared_fifo (
            .clk(clk), .rst(rst), .valid(in_valid && legal_shared), .data(in_data),
            .ready(sr), .pop(sp), .head_view(sh), .next_view(st), .view_count(sn));
        if (MODE == 1) begin: fifo_only
            wire lp, rp;
            assign sp = direction ? rp : lp;
            cse_packetizer #(.WIDTH(SHARED_WIDTH)) left_sender (
                .clk(clk), .rst(rst), .active(!direction), .ready(out_ready[1]),
                .head_view(direction ? 256'b0 : sh), .next_view(direction ? 256'b0 : st),
                .view_count(sn), .pop(lp), .data(left_data), .units(left_units));
            cse_packetizer #(.WIDTH(SHARED_WIDTH)) right_sender (
                .clk(clk), .rst(rst), .active(direction), .ready(out_ready[2]),
                .head_view(direction ? sh : 256'b0), .next_view(direction ? st : 256'b0),
                .view_count(sn), .pop(rp), .data(right_data), .units(right_units));
        end else begin: shared_sender
            wire [SHARED_WIDTH-1:0] beat;
            wire [3:0] count;
            cse_packetizer #(.WIDTH(SHARED_WIDTH)) sender (
                .clk(clk), .rst(rst), .active(1'b1), .ready(direction ? out_ready[2] : out_ready[1]),
                .head_view(sh), .next_view(st), .view_count(sn), .pop(sp), .data(beat), .units(count));
            assign left_data = direction ? {SHARED_WIDTH{1'b0}} : beat;
            assign right_data = direction ? beat : {SHARED_WIDTH{1'b0}};
            assign left_units = direction ? 4'b0 : count;
            assign right_units = direction ? count : 4'b0;
        end
    end endgenerate
endmodule

// Word storage and simultaneous enqueue/dequeue; no serialization state here.
module cse_fifo #(parameter integer DEPTH = 2) (
    input wire clk, rst, valid, pop,
    input wire [255:0] data,
    output wire ready,
    output reg [255:0] head_view, next_view,
    output wire [1:0] view_count
);
    localparam integer COUNT_BITS = DEPTH == 1 ? 1 : 2;
    reg [COUNT_BITS-1:0] count;
    reg [255:0] head;
    wire [255:0] tail;
    wire push = valid && ready;
    assign ready = count < DEPTH;
    assign view_count = count + push;
    generate if (DEPTH == 2) begin: lookahead
        reg [255:0] tail_reg;
        assign tail = tail_reg;
        always @(posedge clk) if (!rst) tail_reg <= next_view;
    end else begin: no_lookahead
        assign tail = 256'b0;
    end endgenerate
    always @* begin
        head_view = head;
        next_view = tail;
        if (push) begin
            if (count == 0) head_view = data;
            else next_view = data;
        end
    end
    always @(posedge clk) begin
        if (rst) count <= 0;
        else begin
            count <= view_count - pop;
            head <= pop ? next_view : head_view;
        end
    end
endmodule

// Full-width ready/stop feedback; valid units are 32-bit lanes. A 160-bit
// beat can contain the tail of head_view and the beginning of next_view.
module cse_packetizer #(parameter integer WIDTH = 160) (
    input wire clk, rst, active, ready,
    input wire [255:0] head_view, next_view,
    input wire [1:0] view_count,
    output wire pop,
    output wire [WIDTH-1:0] data,
    output wire [3:0] units
);
    generate if (WIDTH == 256) begin: full_word
        assign units = active && ready && view_count != 0 ? 4'd8 : 4'd0;
        assign pop = units != 0;
        assign data = head_view;
    end else begin: serial_word
        localparam integer OUT_UNITS = WIDTH / 32;
        localparam integer STEP = WIDTH == 128 ? 4 : 1;
        localparam integer PHASE_BITS = WIDTH == 128 ? 1 : 3;
        reg [PHASE_BITS-1:0] phase;
        wire [2:0] offset = phase * STEP;
        wire [4:0] available = {view_count, 3'b000} - {2'b0, offset};
        wire [3:0] advance = offset + units;
        wire [511:0] window = {next_view, head_view} >> (offset * 32);
        assign units = active && ready && view_count != 0 ?
                       (available < OUT_UNITS ? available[3:0] : OUT_UNITS) : 4'd0;
        assign pop = advance >= 8;
        assign data = active ? window[WIDTH-1:0] : {WIDTH{1'b0}};
        always @(posedge clk) begin
            if (rst) phase <= 0;
            else if (units != 0) phase <= advance / STEP;
        end
    end endgenerate
endmodule
