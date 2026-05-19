import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge
import math

async def reset_dut(dut, sel=0):
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.ui_in.value  = (sel & 0x3) << 6
    dut.uio_in.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1


def pack_input(data_6bit, sel_2bit):
    return ((sel_2bit & 0x3) << 6) | (data_6bit & 0x3F)


def python_boxcar(samples, N):
    """
    Reference model matching hardware: data_out = next_sum >> shift
    (sum AFTER this cycle's update, registered on the same edge).
    """
    buf   = [0] * 32
    ptr   = 0
    rsum  = 0
    count = 0
    shift = int(math.log2(N))
    mask  = N - 1
    outputs, valids = [], []

    for s in samples:
        oldest = buf[ptr]
        full   = (count >= N)
        if full:
            rsum = rsum - oldest + s
        else:
            rsum = rsum + s
        buf[ptr] = s
        ptr = (ptr + 1) & mask
        if count < N:
            count += 1
        valids.append(count >= N)
        outputs.append(rsum >> shift)   # new sum, same as hardware data_out

    return outputs, valids


async def clock_in_sample(dut, data_6bit, sel_2bit):
    dut.ui_in.value = pack_input(data_6bit, sel_2bit)
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_reset(dut):
    """After reset all outputs must be zero and valid must be low."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert dut.uo_out.value  == 0, f"uo_out should be 0 after reset, got {dut.uo_out.value}"
    assert dut.uio_out.value == 0, f"valid should be 0 after reset, got {dut.uio_out.value}"
    dut._log.info("PASS: reset test")


@cocotb.test()
async def test_valid_flag(dut):
    """valid must stay LOW for cycles 0..N-2, then go HIGH at cycle N-1 and stay high."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    SEL, N = 0b00, 4
    await reset_dut(dut)
    for i in range(N + 4):
        await clock_in_sample(dut, data_6bit=10, sel_2bit=SEL)
        await FallingEdge(dut.clk)
        valid_bit = int(dut.uio_out.value) & 0x1
        if i < N - 1:
            assert valid_bit == 0, \
                f"valid should be LOW at cycle {i+1} ({i+1}/{N} samples), got {valid_bit}"
        else:
            assert valid_bit == 1, \
                f"valid should be HIGH at cycle {i+1} (buffer full), got {valid_bit}"
    dut._log.info(f"PASS: valid flag asserts exactly at cycle {N}")


@cocotb.test()
async def test_all_windows(dut):
    """Feed a ramp (1..63) into all four window sizes and verify against reference."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    configs = [(0b00, 4), (0b01, 8), (0b10, 16), (0b11, 32)]
    samples = list(range(1, 64))
    for sel, N in configs:
        dut._log.info(f"Testing N={N} (sel={sel:02b})")
        await reset_dut(dut, sel=sel)
        ref_out, ref_valid = python_boxcar(samples, N)
        for i, s in enumerate(samples):
            await clock_in_sample(dut, data_6bit=s, sel_2bit=sel)
            await FallingEdge(dut.clk)
            hw_out   = int(dut.uo_out.value)
            hw_valid = int(dut.uio_out.value) & 0x1
            assert hw_valid == int(ref_valid[i]), (
                f"N={N} cycle {i+1}: valid expected {int(ref_valid[i])}, got {hw_valid}"
            )
            if ref_valid[i]:
                assert hw_out == ref_out[i], (
                    f"N={N} cycle {i+1}: output expected {ref_out[i]}, got {hw_out}"
                )
        dut._log.info(f"PASS: N={N} — {len(samples)} samples matched reference")


@cocotb.test()
async def test_window_switch(dut):
    """Switch from N=4 to N=16 mid-stream; valid must drop then re-assert after 16 samples."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut._log.info("Phase 1: N=4, 20 samples")
    for _ in range(20):
        await clock_in_sample(dut, data_6bit=20, sel_2bit=0b00)
    await FallingEdge(dut.clk)
    assert (int(dut.uio_out.value) & 0x1) == 1, "valid should be HIGH before window switch"

    dut._log.info("Phase 2: switching to N=16")
    NEW_N, NEW_SEL = 16, 0b10

    await clock_in_sample(dut, data_6bit=40, sel_2bit=NEW_SEL)
    await FallingEdge(dut.clk)
    assert (int(dut.uio_out.value) & 0x1) == 0, \
        "valid should go LOW immediately after window switch"

    ref_out, ref_valid = python_boxcar([40] * 60, NEW_N)
    for i in range(60):
        await clock_in_sample(dut, data_6bit=40, sel_2bit=NEW_SEL)
        await FallingEdge(dut.clk)
        hw_valid = int(dut.uio_out.value) & 0x1
        hw_out   = int(dut.uo_out.value)
        assert hw_valid == int(ref_valid[i]), (
            f"Post-switch cycle {i+1}: valid expected {int(ref_valid[i])}, got {hw_valid}"
        )
        if ref_valid[i]:
            assert hw_out == ref_out[i], (
                f"Post-switch cycle {i+1}: output expected {ref_out[i]}, got {hw_out}"
            )
    dut._log.info("PASS: window switch test")
