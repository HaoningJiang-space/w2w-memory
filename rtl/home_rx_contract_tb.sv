`timescale 1ns/1ps
// Compare the specialized Home receiver against the archived generic behavior.
// Only the legal full-word input contract is assumed; backpressure is arbitrary.
module home_rx_contract_tb;
    reg clk=0;
    always #1 clk=~clk;
    reg rst=1, valid=0, ready=0;
    reg [255:0] data=0;
    wire ar, br, av, bv;
    wire [255:0] ad, bd;
    integer cycle, lane, accepted=0, delivered=0, replacements=0, stalls=0;
    integer seed=20261007;
    endpoint_rx #(.WIDTH(256)) actual (
        .clk(clk),.rst(rst),.beat_valid(valid),.beat_ready(ar),
        .beat_data(data),.beat_units(4'd8),.word_valid(av),
        .word_ready(ready),.word_data(ad));
    endpoint_rx #(.WIDTH(256),.GENERIC_REFERENCE(1)) reference (
        .clk(clk),.rst(rst),.beat_valid(valid),.beat_ready(br),
        .beat_data(data),.beat_units(4'd8),.word_valid(bv),
        .word_ready(ready),.word_data(bd));
    initial begin
        seed=$urandom(seed);
        for (cycle=0;cycle<100004;cycle=cycle+1) begin
            @(negedge clk);
            // Hold the source payload while stalled. Directed full-rate and
            // long-stall intervals precede random traffic and a mid-run reset.
            if (!valid || ar || rst) begin
                valid=cycle<1000 || ($urandom_range(0,3)!=0);
                for (lane=0;lane<8;lane=lane+1) data[32*lane+:32]=$urandom;
            end
            rst=cycle<2 || cycle==50000;
            ready=cycle<1000 || (cycle>=2000 && $urandom_range(0,3)!=0);
            if (cycle>100000) begin valid=0; ready=1; end
            @(posedge clk);
            if (ar!==br || av!==bv || actual.pending_bits!==reference.pending_bits)
                $fatal(1,"Home control mismatch at cycle %0d",cycle);
            if (av && ad!==bd) $fatal(1,"Home payload mismatch at cycle %0d",cycle);
            if (!rst) begin
                if (valid && ar) accepted=accepted+1;
                if (av && ready) delivered=delivered+1;
                if (valid && ar && av && ready) replacements=replacements+1;
                if (av && !ready) stalls=stalls+1;
            end
        end
        if (av || accepted<10000 || replacements<1000 || stalls<1000)
            $fatal(1,"Home contract coverage/drain failure");
        $display("HOME_RX_CONTRACT_PASS cycles=%0d accepted=%0d delivered=%0d replacements=%0d stalls=%0d",
                 cycle,accepted,delivered,replacements,stalls);
        $finish;
    end
endmodule
