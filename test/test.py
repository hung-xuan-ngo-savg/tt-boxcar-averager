import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge
import math


async def reset_dut(dut):
    """Hard reset for 5 cycles. No sel parameter needed —
    the initialized flag in hardware prevents spurious soft-resets
    on the first cycle after reset regardless of sel value."""
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1


def pack_input(data_6bit, sel_2bit):
    return ((sel_2bit & 0x3) << 6) | (data_6bit & 0x3F)


def python_boxcar(samples, N):
    """Reference model matching hardware exactly — uses old_sum
    to match the 1-cycle registered output delay."""
    buf     = [0] * 32
    ptr     = 0
    rsum    = 0
    count   = 0
    shift   = int(math.log2(N))
    mask    = N - 1
    outputs, valids = [], []

    for s in samples:
        oldest   = buf[ptr]
        old_sum  = rsum
        if count >= N:
            rsum = rsum - oldest + s
        else:
            rsum = rsum + s
        buf[ptr] = s
        ptr      = (ptr + 1) & mask
        if count < N:
            count += 1
        valids.append(count >= N)
        outputs.append(old_sum >> shift)

    return outputs, valids


async def clock_in_sample(dut, data_6bit, sel_2bit):
    dut.ui_in.value = pack_input(data_6bit, sel_2bit)
    await RisingEdge(dut.clk)


# ── TEST 1: Reset ──────────────────────────────────────────────

@cocotb.test()
async def test_reset(dut):
    """After reset all outputs must be zero and valid must be low."""
    cocotb.start_soon(Clock(dut.clk, 50, unit="ns").start())
    await reset_dut(dut)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert dut.uo_out.value  == 0, f"uo_out not 0 after reset: {dut.uo_out.value}"
    assert dut.uio_out.value == 0, f"valid not 0 after reset: {dut.uio_out.value}"
    dut._log.info("PASS: reset test")


# ── TEST 2: Valid flag timing ──────────────────────────────────

@cocotb.test()
async def test_valid_flag(dut):
    """valid stays LOW for cycles 0..N-2, HIGH from cycle N-1 onward."""
    cocotb.start_soon(Clock(dut.clk, 50, unit="ns").start())
    SEL, N = 0b00, 4
    await reset_dut(dut)

    for i in range(N + 4):
        await clock_in_sample(dut, data_6bit=10, sel_2bit=SEL)
        await FallingEdge(dut.clk)
        valid_bit = int(dut.uio_out.value) & 0x1
        if i < N - 1:
            assert valid_bit == 0, \
                f"valid should be LOW at cycle {i+1}, got {valid_bit}"
        else:
            assert valid_bit == 1, \
                f"valid should be HIGH at cycle {i+1}, got {valid_bit}"

    dut._log.info(f"PASS: valid flag asserts exactly at cycle {N}")


# ── TEST 3: Correct average, all window sizes ──────────────────

@cocotb.test()
async def test_all_windows(dut):
    """Ramp input 1..63 must match Python reference for all 4 window sizes."""
    cocotb.start_soon(Clock(dut.clk, 50, unit="ns").start())

    configs = [(0b00, 4), (0b01, 8), (0b10, 16), (0b11, 32)]
    samples = list(range(1, 64))

    for sel, N in configs:
        dut._log.info(f"Testing N={N} (sel={sel:02b})")
        await reset_dut(dut)
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

        dut._log.info(f"PASS: N={N} — {len(samples)} samples matched")


# ── TEST 4: Window switch mid-stream ───────────────────────────

@cocotb.test()
async def test_window_switch(dut):
    """Switch N=4 → N=16 mid-stream. valid drops then re-asserts after 16 cycles."""
    cocotb.start_soon(Clock(dut.clk, 50, unit="ns").start())
    await reset_dut(dut)

    dut._log.info("Phase 1: N=4, 20 samples")
    for _ in range(20):
        await clock_in_sample(dut, data_6bit=20, sel_2bit=0b00)
    await FallingEdge(dut.clk)
    assert (int(dut.uio_out.value) & 0x1) == 1, "valid should be HIGH before switch"

    dut._log.info("Phase 2: switching to N=16")
    NEW_N, NEW_SEL = 16, 0b10

    # First cycle with new sel triggers soft reset
    await clock_in_sample(dut, data_6bit=40, sel_2bit=NEW_SEL)
    await FallingEdge(dut.clk)
    assert (int(dut.uio_out.value) & 0x1) == 0, "valid should drop after switch"

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

    dut._log.info("PASS: window switch — re-filled in 16 cycles, output correct")
