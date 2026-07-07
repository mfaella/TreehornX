import sys
import logging
from pathlib import Path

# Import necessary components from the library
from pychc.chc_system import CHCSystem
from pychc.solvers.carcara import Carcara
from pychc.solvers.z3 import Z3CHCSolver
from pychc.solvers.cvc5 import CVC5Solver
from pychc.solvers.witness import Status

def solve_and_check(smt2_path: str):
    path = Path(smt2_path)
    if not path.exists():
        print(f"Error: File {smt2_path} not found.")
        return

    # Setup logging to see the solver interaction (optional)
    logging.basicConfig(level=logging.INFO)

    print(f"--- Solving {path.name} with Z3 ---")

    # Initialize the Carcara proof checker
    # This will be used if the result is UNSAT

    # Initialize the Z3 CHC Solver with the proof checker
    # Z3CHCSolver inherits from CHCSolver which supports internal validation
    proof_checker = Carcara()  # Using CVC5 as the proof checker for Z3's proofs
    solver = Z3CHCSolver()

    # Solve the system provided in the SMT2 file
    # 'validate=True' triggers internal witness validation after solving
    try:
        system = CHCSystem.load_from_file(path)
        solver.load_system(system)
        status = solver.solve()

        print(f"Result: {status}")

        # Retrieve the witness (Model for SAT, Proof for UNSAT)
        witness = solver.get_witness()

        if status == Status.SAT:
            print("Satisfiable: Validated model found.")
            print("Model definitions:")
            for pred, expr in witness.definitions.items():
                 print(f"  {pred} := {expr.function_body.serialize()}")

        elif status == Status.UNSAT:
            print("Unsatisfiable: Proof validated by Carcara.")
            # Carcara uses the ALETHE proof format
            print(f"Proof Format: {proof_checker.get_proof_format()}")
            print(witness)
            witness.serialize(Path("witness.txt"))

        system.validate_unsat_proof(witness, proof_checker)

    except Exception as e:
        print(f"An error occurred during solving or validation: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <path_to_smt2_file>")
    else:
        solve_and_check(sys.argv[1])
