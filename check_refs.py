#!/usr/bin/env python3
"""Smoke test: solve a built-in case and diff it against the author's solution.

This is the control that was never run.  Every built-in test carries hand-tuned
root brackets, so a built-in case is the only path through this solver with a
known-correct expected answer; running one before touching the user-defined
case (0) is what separates "my inputs are wrong" from "the solver cannot do
this".

The comparison is made away from the wave positions.  Wave speeds are the one
thing two builds legitimately disagree about at the last digits, and the two
files put their inserted grid points in slightly different places, so a
pointwise diff of the whole profile is dominated by an O(1) offset at every
discontinuity and says nothing.  What is compared instead is the value on each
constant state: the reference's plateaus are located, and the freshly solved
profile is read at the centre of each.

Usage:
    ./check_refs.py [--case N] [--tol T] [--refdir DIR] [--keep]

Exit status is 0 only if every constant state of every case agrees to --tol.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# resources/Exact_Riemann_Solver -> the project's papers/ directory.
DEFAULT_REFDIR = os.path.normpath(os.path.join(
    HERE, "..", "..", "papers", "2006-giacomazzo-rezzolla",
    "reference-solutions", "exact_solutions"))

# initial_data -> (reference directory, solver answers after the case number).
# Prompt order is initial_data, EOS, x_left, x_right, time, nx, accuracy,
# verbose; the domain and time are the ones the published files were made with.
CASES = {
    8: ("Balsara1", ["1", "-0.5", "0.5", "0.4", "1000", "1.0e-10", "1"]),
    9: ("Balsara2", ["1", "-0.5", "0.5", "0.4", "1000", "1.0e-10", "1"]),
    10: ("Balsara3", ["1", "-0.5", "0.5", "0.4", "1000", "1.0e-10", "1"]),
    11: ("Balsara4", ["1", "-0.5", "0.5", "0.4", "100", "1.0e-10", "1"]),
    # Balsara 5 is the one published case with a genuinely non-coplanar
    # rotation, so it is the only entry here that makes the solver's 5x5
    # Alfven Newton do real work -- see docs/exact-solver-alfven-system.md.
    # MEASURED 2026-09-11: at the published parameters below it does NOT
    # converge in 2400 s; it had emitted one iteration block after 40 minutes.
    # So it is not a usable oracle as it stands, and it is deliberately out of
    # the default CHECK_CASES.  Left here, with the timeout override, because
    # it is the entry someone will reach for when the Alfven path needs a
    # check; they should know the cost before starting.
    12: ("Balsara5_psi", ["1", "-0.5", "0.5", "0.55", "1000", "1.0e-10", "1"]),
    # Case 13, the generic Alfven test, is DELIBERATELY ABSENT.  initialdata.f90
    # gives it gamma = 5/3, while the reference run's own RInput.txt, shipped
    # beside the published solution, says 1.6666.  That 4e-5 difference moves
    # the intermediate total pressure by 2.1e-5 and looks exactly like a solver
    # defect; with gamma = 1.6666 the solver reproduces the reference to
    # 1.0e-12.  Adding it here means overriding gamma first.
}
# Cases 12 and 13 solve in minutes, not seconds; raise this for them.
TIMEOUT = int(os.environ.get("CHECK_REFS_TIMEOUT", "300"))
COLUMNS = ["rho", "ptot", "vx", "vy", "vz", "By", "Bz"]


def plateaus(a, w=6, tol=1e-9):
    """Rows of `a` whose every field is constant over a +-w window."""
    n = len(a)
    flat = np.ones(n, bool)
    for c in range(1, 8):
        scale = max(float(np.ptp(a[:, c])), 1e-30)
        loc = np.array([np.ptp(a[max(0, i - w):i + w + 1, c]) for i in range(n)])
        flat &= loc / scale < tol
    return flat


def segments(flag):
    out, i = [], 0
    while i < len(flag):
        if flag[i]:
            j = i
            while j + 1 < len(flag) and flag[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def compare(ref, new):
    """Max abs deviation on each of the reference's constant states."""
    fn = plateaus(new)
    if not fn.any():
        raise SystemExit("check_refs: the fresh solution has no constant state")
    cand = np.where(fn)[0]
    worst, rows = 0.0, []
    for (i, j) in segments(plateaus(ref)):
        xm = 0.5 * (ref[i, 0] + ref[j, 0])
        k = cand[np.argmin(np.abs(new[cand, 0] - xm))]
        d = np.abs(ref[i:j + 1].mean(0)[1:] - new[k, 1:])
        rows.append((ref[i, 0], ref[j, 0], int(np.argmax(d)), float(d.max())))
        worst = max(worst, float(d.max()))
    return worst, rows


def run_case(case, outdir):
    answers = [str(case)] + CASES[case][1]
    # Own process group, and kill the group on a timeout.  subprocess.run's
    # timeout kills only the direct child, run_solver.sh; the solver it exec'd
    # is a grandchild and survives -- a timed-out case left a riemann_rmhd
    # running for half an hour on a deleted temporary directory.
    p = subprocess.Popen([os.path.join(HERE, "run_solver.sh"), "-o", outdir,
                          *answers], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True,
                         start_new_session=True)
    try:
        out, err = p.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        p.communicate()
        raise SystemExit(f"check_refs: case {case} timed out after {TIMEOUT} s "
                         f"(raise CHECK_REFS_TIMEOUT)")
    p = types.SimpleNamespace(returncode=p.returncode, stdout=out, stderr=err)
    got = os.path.join(outdir, "solution_last.dat")
    if p.returncode != 0 or not os.path.exists(got) or os.path.getsize(got) == 0:
        raise SystemExit(f"check_refs: case {case} did not produce a solution\n"
                         + (p.stdout or "") + (p.stderr or ""))
    return np.loadtxt(got)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, action="append", choices=sorted(CASES),
                    help="built-in case to check (repeatable; default 8)")
    ap.add_argument("--tol", type=float, default=1.0e-7,
                    help="max allowed deviation on a constant state")
    ap.add_argument("--refdir", default=DEFAULT_REFDIR)
    ap.add_argument("--keep", action="store_true", help="keep the run directory")
    args = ap.parse_args()

    cases = args.case or [8]
    tmp = tempfile.mkdtemp(prefix="check_refs-")
    failed = []
    try:
        for case in cases:
            name = CASES[case][0]
            path = os.path.join(args.refdir, name, "solution_last.dat")
            if not os.path.exists(path):
                raise SystemExit(f"check_refs: no reference at {path}")
            ref = np.loadtxt(path)
            new = run_case(case, os.path.join(tmp, name))
            worst, rows = compare(ref, new)
            print(f"case {case} ({name}): {len(rows)} constant states, "
                  f"{len(ref)} reference rows")
            for (xa, xb, ic, d) in rows:
                print(f"    x in [{xa:+.4f}, {xb:+.4f}]  max|d| = {d:.3e}"
                      f"  ({COLUMNS[ic]})")
            verdict = "PASS" if worst <= args.tol else "FAIL"
            print(f"    worst = {worst:.3e}   tol = {args.tol:.1e}   {verdict}")
            if worst > args.tol:
                failed.append(case)
    finally:
        if args.keep:
            print(f"run directory kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    if failed:
        print(f"check_refs: FAILED for case(s) {failed}")
        return 1
    print("check_refs: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
