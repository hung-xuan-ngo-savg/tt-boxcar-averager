module window_decoder (
    input  wire [1:0] sel,
    output reg  [5:0] window_size,
    output reg  [2:0] shift_amt
);
    always @(*) begin
        case (sel)
            2'b00: begin window_size = 6'd4;  shift_amt = 3'd2; end
            2'b01: begin window_size = 6'd8;  shift_amt = 3'd3; end
            2'b10: begin window_size = 6'd16; shift_amt = 3'd4; end
            2'b11: begin window_size = 6'd32; shift_amt = 3'd5; end
        endcase
    end
endmodule