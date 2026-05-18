/*
 * Copyright (c) 2024 Hung Xuan (Simon) Ngo
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_boxcar_avg (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  wire _unused = &{ena, uio_in};

  wire [7:0] avg_out;
  wire       avg_valid;

  boxcar_core u_core (
        .clk      (clk),
        .rst_n    (rst_n),
        .data_in  ({2'b00, ui_in[5:0]}),
        .sel      (ui_in[7:6]),
        .data_out (avg_out),
        .valid    (avg_valid)
    );

  assign uo_out  = avg_out;
  assign uio_out = {7'b0, avg_valid};
  assign uio_oe  = 8'b0000_0001;

endmodule
