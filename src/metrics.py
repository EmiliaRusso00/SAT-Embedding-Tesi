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
            "num_edges": logical_graph.number_of_edges(),
        },
        "physical_graph": {
            "num_vertices": physical_graph.number_of_nodes(),
            "num_edges": physical_graph.number_of_edges(),
        },
        "sat_encoding": {
            "num_variables": num_vars,
            "num_clauses": num_clauses,
            "encoding_type": encoding_type,
        },
        "solver": {
            "name": solver_name,
            "status": status,
            "time_cnf_generation": time_cnf,
            "time_sat_solve": time_sat,
            "time_total": time_cnf + time_sat,
        },
    }

    if solver_error is not None:
        out["solver"]["error"] = solver_error

    # Prepare unsat list (expected as list[dict])
    unsat_list = unsat_clauses if unsat_clauses is not None else None

    # If we will render a custom solver block (to embed unsat_clauses with
    # compact arrays), pop `solver` now so base_json won't already contain it
    # (which would cause a duplicated key when we inject our custom block).
    solver_for_block = out.pop("solver", None)

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
    # Build solver block: if we have unsat clauses we will insert them
    # with compact inline arrays; otherwise reuse the normal json.dumps.
    if unsat_list is None:
        solver_block = json.dumps(solver_for_block or {}, indent=4)
        solver_block = "\n".join("    " + ln for ln in solver_block.splitlines())
    else:
        solver_without_unsat = solver_for_block or {}
        solver_block = json.dumps(solver_without_unsat, indent=4)
        solver_lines = solver_block.splitlines()
        # remove final closing brace '}' to append unsat_clauses
        if solver_lines and solver_lines[-1].strip() == "}":
            solver_lines = solver_lines[:-1]
        # ensure last line ends with a comma so we can add a new field
        if solver_lines:
            if not solver_lines[-1].rstrip().endswith(','):
                solver_lines[-1] = solver_lines[-1] + ','

        unsat_block = []
        unsat_block.append('    "unsat_clauses": [')
        for entry in unsat_list:
            etype = entry.get("type", "unknown")
            clause = entry.get("clause", [])
            lp = entry.get("logical_pair", [])
            pp = entry.get("physical_pair", [])

            unsat_block.append('        {')
            unsat_block.append(f'            "type": "{etype}",')
            unsat_block.append('            "clause": ' + json.dumps(clause, separators=(',',':')) + ',')
            unsat_block.append('            "logical_pair": ' + json.dumps(lp, separators=(',',':')) + ',')
            unsat_block.append('            "physical_pair": ' + json.dumps(pp, separators=(',',':')))
            unsat_block.append('        },')

        # remove trailing comma of last item (if any entries)
        if len(unsat_list) > 0:
            for i in range(len(unsat_block)-1, -1, -1):
                if unsat_block[i].strip().endswith('},'):
                    unsat_block[i] = unsat_block[i].rstrip(',')
                    break

        unsat_block.append('    ]')

        solver_lines.extend(unsat_block)
        solver_lines.append('}')
        solver_block = "\n".join("    " + ln for ln in solver_lines)

    final_json = (
        base_json[:-2]
        + ",\n    \"solver\": "
        + solver_block
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
