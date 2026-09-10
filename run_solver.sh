#!/usr/bin/env bash
#
# Run the exact Riemann solver in a private scratch directory.
#
# The solver hard-codes its filenames: it reads RInput.txt, VxGuess.txt and
# CaseZeroBounds.txt from the current directory and writes solution.dat,
# solution_last.dat, solution.sol, exact.sol, funcv.dat, vel_func.dat and
# friends back into it. Two runs started in the same directory therefore
# overwrite each other's inputs and interleave their output. This script gives
# each run its own directory: it copies the binary and the input files there,
# runs, and prints the path.
#
# Usage:
#   ./run_solver.sh [-o OUTDIR] [-i INPUTDIR] [-k] [answers...]
#
#   -o OUTDIR    run here instead of a fresh runs/<timestamp>-<pid> directory
#   -i INPUTDIR  take RInput.txt and the seed files from here (default: repo root)
#   -k           keep going if OUTDIR already exists and is non-empty
#   answers...   the solver's interactive prompts, one argument per prompt, fed
#                on stdin. With none given, stdin is passed through unchanged.
#
# Prompt order: initial_data, EOS, x_left, x_right, time, nx, accuracy, verbose
#
# Example (Balsara 1, the paper's parameters):
#   ./run_solver.sh 8 1 -0.5 0.5 0.4 1000 1.0e-10 1
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$REPO/riemann_rmhd"
INPUTDIR="$REPO"
OUTDIR=""
FORCE=0

while getopts ":o:i:kh" opt; do
  case "$opt" in
    o) OUTDIR="$OPTARG" ;;
    i) INPUTDIR="$OPTARG" ;;
    k) FORCE=1 ;;
    h) sed -n '2,28p' "${BASH_SOURCE[0]}"; exit 0 ;;
    \?) echo "run_solver.sh: unknown option -$OPTARG" >&2; exit 2 ;;
    :)  echo "run_solver.sh: -$OPTARG needs an argument" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

if [ ! -x "$BIN" ]; then
  echo "run_solver.sh: $BIN not found or not executable; run 'make' first" >&2
  exit 1
fi
if [ ! -d "$INPUTDIR" ]; then
  echo "run_solver.sh: input directory '$INPUTDIR' does not exist" >&2
  exit 1
fi
if [ ! -f "$INPUTDIR/RInput.txt" ]; then
  echo "run_solver.sh: no RInput.txt in '$INPUTDIR'" >&2
  exit 1
fi

if [ -z "$OUTDIR" ]; then
  OUTDIR="$REPO/runs/$(date +%Y%m%d-%H%M%S)-$$"
fi
if [ -e "$OUTDIR" ] && [ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ] && [ "$FORCE" -eq 0 ]; then
  echo "run_solver.sh: '$OUTDIR' already exists and is not empty; use -k to reuse it" >&2
  exit 1
fi
mkdir -p "$OUTDIR"
OUTDIR="$(cd "$OUTDIR" && pwd)"

cp "$BIN" "$OUTDIR/"
cp "$INPUTDIR/RInput.txt" "$OUTDIR/"
# Optional; only case (0) reads these.
for f in VxGuess.txt CaseZeroBounds.txt VxGuessCD.txt; do
  [ -f "$INPUTDIR/$f" ] && cp "$INPUTDIR/$f" "$OUTDIR/"
done

status=0
if [ "$#" -gt 0 ]; then
  printf '%s\n' "$@" | (cd "$OUTDIR" && ./riemann_rmhd) > "$OUTDIR/run.log" 2>&1 || status=$?
else
  (cd "$OUTDIR" && ./riemann_rmhd) > "$OUTDIR/run.log" 2>&1 || status=$?
fi

# solution.dat holds every solver iteration appended in turn; the last block is
# the converged solution, which is what the published reference files contain.
# Two passes -- find the last iteration marker, then print what follows it --
# rather than accumulating the block in a variable: at nx=20000 the block is
# 26068 lines and mawk quietly produced an EMPTY file for the accumulating
# version, which is the worst possible failure for a reference file.
if [ -s "$OUTDIR/solution.dat" ]; then
  awk 'FNR==NR {if (/iteration number/) last=NR; next}
       FNR>last && !/^[[:space:]]*#/ && NF' \
      "$OUTDIR/solution.dat" "$OUTDIR/solution.dat" \
      > "$OUTDIR/solution_last.dat"
fi

echo "output: $OUTDIR"
if [ "$status" -ne 0 ]; then
  echo "run_solver.sh: solver exited $status; see $OUTDIR/run.log" >&2
fi
exit "$status"
