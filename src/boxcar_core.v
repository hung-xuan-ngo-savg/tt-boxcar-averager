/*
 * Copyright (c) 2024 Hung Xuan Ngo
 * SPDX-License-Identifier: Apache-2.0
 */
module boxcar_core (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  data_in,
    input  wire [1:0]  sel,
    output reg  [7:0]  data_out,
    output reg         valid
);
    wire [5:0] window_size;
    wire [2:0] shift_amt;

    window_decoder u_decoder (
        .sel         (sel),
        .window_size (window_size),
        .shift_amt   (shift_amt)
    );

    reg [7:0]  buffer [0:31];
    reg [4:0]  wr_ptr;
    reg [12:0] running_sum;
    reg [5:0]  sample_count;
    reg [1:0]  sel_prev;

    wire [4:0]  ptr_mask          = window_size[4:0] - 5'd1;
    wire [12:0] data_in_ext       = {5'b0, data_in};
    wire [12:0] oldest_sample_ext = {5'b0, buffer[wr_ptr]};
    wire        window_full       = sample_count >= window_size;

    // next_sum holds the sum AFTER this cycle's update.
    // Registering it into data_out on the next edge makes the
    // GL netlist glitch-free (no combinatorial path to output).
    reg [12:0] next_sum;

    always @(*) begin
        if (window_full)
            next_sum = running_sum - oldest_sample_ext + data_in_ext;
        else
            next_sum = running_sum + data_in_ext;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sel_prev     <= sel;   // match sel — avoids spurious switch after reset
            wr_ptr       <= 5'd0;
            running_sum  <= 13'd0;
            sample_count <= 6'd0;
            valid        <= 1'b0;
            data_out     <= 8'd0;
            // No for-loop: window_full=0 protects running_sum from stale buffer data
        end else begin
            if (sel != sel_prev) begin
                sel_prev     <= sel;
                wr_ptr       <= 5'd0;
                running_sum  <= 13'd0;
                sample_count <= 6'd0;
                valid        <= 1'b0;
                data_out     <= 8'd0;
            end else begin
                sel_prev    <= sel;
                running_sum <= next_sum;

                buffer[wr_ptr] <= data_in;
                wr_ptr         <= (wr_ptr + 5'd1) & ptr_mask;

                if (sample_count < window_size)
                    sample_count <= sample_count + 6'd1;

                valid    <= sample_count >= window_size - 6'd1;
                data_out <= next_sum[12:0] >> shift_amt;
            end
        end
    end

endmodule
