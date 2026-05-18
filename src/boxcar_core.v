 
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
 
    wire [4:0] ptr_mask = window_size[4:0] - 5'd1;
 
    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // FIX: was `sel_prev <= sel` — resetting a register to a live input
            // creates a non-const async reset, which Yosys infers as $aldff.
            // $aldff expands to $_ALDFF_PN_ which has no sky130 mapping → GDS fails.
            // Reset to a constant instead. On the first clock after reset, if sel
            // differs from 2'b00 the `else if` branch fires and re-initialises anyway.
            sel_prev     <= 2'b00;
            wr_ptr       <= 5'd0;
            running_sum  <= 13'd0;
            sample_count <= 6'd0;
            valid        <= 1'b0;
            data_out     <= 8'd0;
            for (i = 0; i < 32; i = i + 1)
                buffer[i] <= 8'd0;
 
        end else if (sel != sel_prev) begin
            sel_prev     <= sel;
            wr_ptr       <= 5'd0;
            running_sum  <= 13'd0;
            sample_count <= 6'd0;
            valid        <= 1'b0;
            data_out     <= 8'd0;
            for (i = 0; i < 32; i = i + 1)
                buffer[i] <= 8'd0;
 
        end else begin
            sel_prev       <= sel;
            running_sum    <= running_sum
                              - 13'(buffer[wr_ptr])
                              + 13'(data_in);
            buffer[wr_ptr] <= data_in;
            wr_ptr         <= (wr_ptr + 5'd1) & ptr_mask;
 
            if (sample_count < window_size)
                sample_count <= sample_count + 6'd1;
 
            if (sample_count >= window_size - 1)
                valid <= 1'b1;
 
            data_out <= 8'(running_sum[12:0] >> shift_amt);
        end
    end
endmodule
