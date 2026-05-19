import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge
import math

async def reset_dut(dut, sel = 0):
    """Pull reset low for 5 cycles then release. No extra cycle after."""
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.ui_in.value  = (sel & 0x3) << 6
    dut.uio_in.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    # *** No extra RisingEdge here ***
    # If we clocked one extra cycle here, sample_count would already be 1
    # before the test loop starts, causing valid to assert one cycle too early.


def pack_input(data_6bit, sel_2bit):
    """Pack 6-bit data + 2-bit sel into one 8-bit ui_in value."""
    return ((sel_2bit & 0x3) << 6) | (data_6bit & 0x3F)


def python_boxcar(samples, N):
    """
    Python reference model — mirrors the hardware EXACTLY including the
    1-cycle output delay (data_out uses the sum BEFORE this cycle's update).
    """
    buf   = [0] * 32
    ptr   = 0
    rsum  = 0
    count = 0
    shift = int(math.log2(N))
    mask  = N - 1
    outputs, valids = [], []

    for s in samples:
        oldest  = buf[ptr]
        old_sum = rsum               # save sum BEFORE update (matches hardware)
        rsum    = rsum - oldest + s
        buf[ptr] = s
        ptr     = (ptr + 1) & mask
        if count < N:
            count += 1
        valids.append(count >= N)
        outputs.append(old_sum >> shift)  # hardware outputs old_sum, not new

    return outputs, valids


async def clock_in_sample(dut, data_6bit, sel_2bit):
    """Drive one sample and clock it in."""
    dut.ui_in.value = pack_input(data_6bit, sel_2bit)
    await RisingEdge(dut.clk)


# ─────────────────────────────────────────────
# TEST 1 — Reset
# ─────────────────────────────────────────────

@cocotb.test()
async def test_reset(dut):
    """After reset all outputs must be zero and valid must be low."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    await RisingEdge(dut.clk)      # one settle cycle
    await FallingEdge(dut.clk)

    assert dut.uo_out.value  == 0, f"uo_out should be 0 after reset, got {dut.uo_out.value}"
    assert dut.uio_out.value == 0, f"valid should be 0 after reset, got {dut.uio_out.value}"
    dut._log.info("PASS: reset test")


# ─────────────────────────────────────────────
# TEST 2 — Valid flag timing
# ─────────────────────────────────────────────

@cocotb.test()
async def test_valid_flag(dut):
    """
    valid must stay LOW for cycles 0..N-2, then go HIGH at cycle N-1 and stay high.
    Tested with N=4 (sel=00).
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    SEL, N = 0b00, 4
    await reset_dut(dut)

    for i in range(N + 4):
        await clock_in_sample(dut, data_6bit=10, sel_2bit=SEL)
        await FallingEdge(dut.clk)

        valid_bit = int(dut.uio_out.value) & 0x1

        if i < N - 1:
            assert valid_bit == 0, \
                f"valid should be LOW at cycle {i+1} (only {i+1}/{N} samples seen), got {valid_bit}"
        else:
            assert valid_bit == 1, \
                f"valid should be HIGH at cycle {i+1} (buffer full), got {valid_bit}"

    dut._log.info(f"PASS: valid flag asserts exactly at cycle {N}")


# ─────────────────────────────────────────────
# TEST 3 — Correct average, all window sizes
# ─────────────────────────────────────────────

@cocotb.test()
async def test_all_windows(dut):
    """
    Feed a ramp (1,2,...,63) into all four window sizes.
    Every output and valid flag must match the Python reference.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    configs  = [(0b00, 4), (0b01, 8), (0b10, 16), (0b11, 32)]
    samples  = list(range(1, 64))

    for sel, N in configs:
        dut._log.info(f"Testing N={N} (sel={sel:02b})")
        await reset_dut(dut, sel = sel)

        ref_out, ref_valid = python_boxcar(samples, N)

        for i, s in enumerate(samples):
            await clock_in_sample(dut, data_6bit=s, sel_2bit=sel)
            await FallingEdge(dut.clk)

            hw_out   = int(dut.uo_out.value)
            hw_valid = int(dut.uio_out.value) & 0x1

            # Check valid flag every cycle
            assert hw_valid == int(ref_valid[i]), (
                f"N={N} cycle {i+1}: valid expected {int(ref_valid[i])}, got {hw_valid}"
            )
            # Check output only once valid is high
            if ref_valid[i]:
                assert hw_out == ref_out[i], (
                    f"N={N} cycle {i+1}: output expected {ref_out[i]}, got {hw_out}"
                )

        dut._log.info(f"PASS: N={N} — {len(samples)} samples all matched reference")


# ─────────────────────────────────────────────
# TEST 5 — Window size switch mid-stream
# ─────────────────────────────────────────────

@cocotb.test()
async def test_window_switch(dut):
    """
    Run N=4 for 20 samples, then switch to N=16.
    Hardware auto-resets on sel change (1 cycle to reset, then re-fills over 16 cycles).
    valid must go LOW immediately after switch, then HIGH again after 16 new samples.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    # ── Phase 1: N=4, 20 samples of value 20 ──
    dut._log.info("Phase 1: N=4, 20 samples")
    for _ in range(20):
        await clock_in_sample(dut, data_6bit=20, sel_2bit=0b00)
    await FallingEdge(dut.clk)
    assert (int(dut.uio_out.value) & 0x1) == 1, "valid should be HIGH before window switch"

    # ── Phase 2: switch to N=16 ──
    dut._log.info("Phase 2: switching to N=16")
    NEW_N, NEW_SEL = 16, 0b10

    # First cycle with new sel — hardware detects sel change and resets.
    # data_in is present but NOT processed (reset cycle).
    await clock_in_sample(dut, data_6bit=40, sel_2bit=NEW_SEL)
    await FallingEdge(dut.clk)
    assert (int(dut.uio_out.value) & 0x1) == 0, \
        "valid should go LOW immediately after window switch (auto-reset)"

    # Now run 60 more cycles — hardware is fresh, behaves as new N=16 boxcar.
    # Python reference also starts fresh.
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

    dut._log.info("PASS: window switch — auto-reset, re-filled in 16 cycles, output correct")
