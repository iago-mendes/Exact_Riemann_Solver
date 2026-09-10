PROG =	riemann_rmhd

SRCS =	Interfaces.f90 initialdata.f90 quartic.f90\
nrutil.f90 lubksb.f90 ludcmp.f90 postshock.f90 riemann_rmhd.f90

OBJS =	Interfaces.o initialdata.o quartic.o\
nrutil.o lubksb.o ludcmp.o postshock.o riemann_rmhd.o

LIBS =	

F90 = gfortran -ffree-line-length-none

all: $(PROG)

$(PROG): $(OBJS)
	$(F90) $(LDFLAGS) -o $@ $(OBJS) $(LIBS)

clean:
	rm -f $(OBJS) $(OBJ_TEST) *.kmo *.mod

data:	
	rm -f *.dat *.sol

tar:
	tar -czvf rmhd_riemann_solver.tgz $(SRCS) Makefile README RInput.txt

.PHONY: all clean data tar run-test check-refs

.SUFFIXES: $(SUFFIXES) .f90

.f90.o:
	$(F90) $(F90FLAGS) -c $<

run-test:
	printf "13\n1\n-2\n2\n1.5\n100\n1.0e-7\n1\n" | ./riemann_rmhd

# Smoke test: solve built-in case 8 (Balsara 1) and diff it against the
# author's published solution, on the constant states only.  This is the one
# path through the solver with a known-correct expected answer; run it before
# trusting anything the user-defined case (0) produces.  Add cases with
# CHECK_CASES="--case 8 --case 9 --case 10".
CHECK_CASES ?= --case 8

check-refs: $(PROG)
	./check_refs.py $(CHECK_CASES)

# DO NOT DELETE
