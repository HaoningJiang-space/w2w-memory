`timescale 1ns/1ps
// Deployment-specialized baseline, NOT a reusable direction-selectable template.
// Both parent implementations receive exactly the same constant binding and
// reject a wrong destination. Keep the full external HB pin interface visible;
// synthesis may eliminate logic on the unused direction, not its physical cost.
module endpoint_fixed_source #(
    parameter integer CONFIGURABLE=0, DIRECTION=0
) (
    input wire clk, rst, cfg_shared_direction,
    input wire native_valid, native_role, native_shared_direction,
    input wire [255:0] native_data,
    output wire native_ready,
    output wire [2:0] hb_valid,
    input wire [2:0] hb_ready,
    output wire [255:0] home_data,
    output wire [159:0] left_data, right_data,
    output wire [3:0] home_units, left_units, right_units
);
    wire legal=!native_role || native_shared_direction==DIRECTION;
    wire ready_internal;
    assign native_ready=legal && ready_internal;
    endpoint_source #(.WIDTH(160),.DEPTH(2),.CONFIGURABLE(CONFIGURABLE)) source (
        .clk(clk),.rst(rst),.cfg_shared_direction(DIRECTION != 0),
        .native_valid(native_valid && legal),.native_role(native_role),
        .native_shared_direction(DIRECTION != 0),.native_data(native_data),
        .native_ready(ready_internal),.hb_valid(hb_valid),.hb_ready(hb_ready),
        .home_data(home_data),.left_data(left_data),.right_data(right_data),
        .home_units(home_units),.left_units(left_units),.right_units(right_units));
endmodule
