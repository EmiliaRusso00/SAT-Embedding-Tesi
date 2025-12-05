import json
from datetime import datetime
from utils import ensure_dir


def write_experiment_output(exp_id, config, logical_graph, physical_graph,
                            num_vars, num_clauses, encoding_type,
                            solver_name, time_cnf, time_sat, status,
                            solution=None, solver_error=None,
                            unsat_clauses=None, output_dir="outputs"):
    
    ensure_dir(output_dir)

    # ----------------------------
    # JSON base (senza solutions)
    # ----------------------------
    out = {
        "experiment_id": exp_id,
        "timestamp": datetime.now().isoformat(),
        "config": config,
        "logical_graph": {
            "num_vertices": logical_graph.number_of_nodes(),
            "num_edges": logical_graph.number_of_edges()
        },
        "physical_graph": {
            "num_vertices": physical_graph.number_of_nodes(),
            "num_edges": physical_graph.number_of_edges()
        },
        "sat_encoding": {
            "num_variables": num_vars,
            "num_clauses": num_clauses,
            "encoding_type": encoding_type
        },
        "solver": {
            "name": solver_name,
            "status": status,
            "time_cnf_generation": time_cnf,
            "time_sat_solve": time_sat,
            "time_total": time_cnf + time_sat
        }
    }

    if solver_error is not None:
        out["solver"]["error"] = solver_error

    if unsat_clauses is not None:
        out["solver"]["unsat_clauses"] = [
            f"[{', '.join(map(str, clause))}, {ctype}]"
            for clause, ctype in unsat_clauses
        ]

    # Dump preliminare senza solutions
    base_json = json.dumps(out, indent=4)
    fname = f"{output_dir}/experiment_{exp_id:03d}.json"

    # ----------------------------
    # COSTRUZIONE SOLUTIONS MANUALE
    # ----------------------------
    if solution is None:
        solutions_str = "null"
        solutions_count = 0
    else:
        solutions_count = len(solution)

        lines = ["["]
        for sol in solution:
            a = sol["assignment"]
            sat = sol.get("sat_time", time_sat)

            # Assignment compatto
            assignment_items = []
            for k, v in a.items():
                if isinstance(v, (list, tuple)):
                    assignment_items.append(f'"{k}": [{v[0]},{v[1]}]')
                else:
                    assignment_items.append(f'"{k}": {v}')
            assignment_str = "{" + ", ".join(assignment_items) + "}"

            line = f'    {{"assignment": {assignment_str}, "sat_time": {sat}}},'
            lines.append(line)

        # Rimuovi trailing comma
        if len(lines) > 1:
            lines[-1] = lines[-1].rstrip(",")

        lines.append("]")
        solutions_str = "\n".join(lines)

    # ----------------------------
    # Inserimento solutions + count nel JSON
    # ----------------------------
    final_json = (
        base_json[:-2]
        + ",\n    \"solutions_count\": "
        + str(solutions_count)
        + ",\n    \"solutions\": "
        + solutions_str
        + "\n}"
    )

    # Salva
    with open(fname, "w") as f:
        f.write(final_json)

    return fname
