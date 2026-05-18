<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

Maintains a circular buffer of up to 32 samples and a 13-bit running sum. Each clock cycle one sample is evicted and one added (O(1)). Division by N is implemented as a right-shift since all window sizes are powers of 2. ui_in[7:6] selects the window size at runtime (00=4, 01=8, 10=16, 11=32). uio_out[0] is a valid flag that goes high once the buffer has been filled.

## How to test

Apply reset (rst_n low). Set ui_in[7:6] to choose window size. Clock in samples on ui_in[5:0]. After N cycles, valid flag (uio_out[0]) goes high and uo_out holds the running average. Change ui_in[7:6] mid-stream to switch window size.

## External hardware

List external hardware used in your project (e.g. PMOD, LED display, etc), if any
