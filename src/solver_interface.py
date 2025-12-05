import multiprocessing as mp
import time
import traceback
from pysat.solvers import Glucose4
from pysat.formula import CNF

def _solve_process(dimacs_path, cnf_gen, assumptions, return_dict):
    try:
        cnf = CNF(from_file=dimacs_path)
        solver = Glucose4(use_timer=True)

        # Aggiungo le clausole AND condizionali sugli assumption
        for idx, clause in enumerate(cnf_gen.clauses):
            aux_lit = cnf_gen.num_vars + idx + 1
            # (¬a_i ∨ C_i)
            solver.add_clause([-aux_lit] + clause)
       
        # Ritorna true se SAT, False se UNSAT
        sat = solver.solve(assumptions=assumptions)

        model = solver.get_model() if sat else None
        core = None
        if not sat:
            print("Sei nella parte UNSAT")
            core = solver.get_core()
            print(model, len(core))

        solver.delete()

        return_dict["status"] = sat
        return_dict["model"] = model
        return_dict["core"] = core
        return_dict["error"] = None

    except Exception as e:
        return_dict["status"] = False
        return_dict["model"] = None
        return_dict["core"] = None
        return_dict["error"] = traceback.format_exc()


def solve_dimacs_file(dimacs_path, timeout_seconds=None, cnf_gen=None):
    """
    Risolve un file DIMACS con timeout funzionante su Windows.
    Usa assumptions per UNSAT core.
    """
    manager = mp.Manager()
    return_dict = manager.dict()

    # Crea assumptions artificiali per ottenere UNSAT core
    assumptions = []
    if cnf_gen:
        for idx, clause in enumerate(cnf_gen.clauses):
            aux_lit = cnf_gen.num_vars + idx + 1
            assumptions.append(aux_lit)

    # Lancia solver in un processo separato
    p = mp.Process(target=_solve_process, args=(dimacs_path, cnf_gen, assumptions, return_dict))
    start = time.time()
    p.start()
    p.join(timeout_seconds)

    time_elapsed = time.time() - start

    if p.is_alive():
        # Timeout → kill!
        p.terminate()
        p.join()
        return {
            "status": "ERROR",
            "time": time_elapsed,
            "model": None,
            "unsat_core": None,
            "error": "Timeout expired"
        }

    # Solver terminato
    sat_flag = return_dict.get("status")
    model = return_dict.get("model")
    error = return_dict.get("error")
    core = return_dict.get("core")

    if error:
        return {
            "status": "ERROR",
            "time": time_elapsed,
            "model": None,
            "unsat_core": None,
            "error": error
        }

    if sat_flag:
        return {
            "status": "SAT",
            "time": time_elapsed,
            "model": model,
            "unsat_core": None
        }

    else:
        # UNSAT
        if core and cnf_gen:
            # traduci literal aux → indice clausola
            core_clause_ids = [
                lit - cnf_gen.num_vars - 1
                for lit in core
                if lit > 0
            ]
        else:
            core_clause_ids = None

        return {
            "status": "UNSAT",
            "time": time_elapsed,
            "model": None,
            "unsat_core": core_clause_ids,
        }
