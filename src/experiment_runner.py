import argparse
import time
import yaml
import os
import json
import networkx as nx

from parser import read_graph, read_graph_json
from cnf_generator import CNFGenerator
from solver_interface import solve_dimacs_file
from metrics import write_experiment_output
from utils import ensure_dir
from plot_utils import plot_embedding, plot_noembedding


# ======================================================================
#  MAIN EXPERIMENT FUNCTION
# ======================================================================
def run_experiment(cfg, skip_reduction=False):  
    exp_id = cfg.get("id", 0)
    variant = cfg.get("variant", "reduced" if not skip_reduction else "full")
    

    print(f"\n[INFO] Running experiment ID: {exp_id} [{variant.upper()}]")

    # Directory separata per variante
    exp_dir = os.path.join(f"outputs/{exp_id}", f"{variant}")
    ensure_dir(exp_dir)

    # ----------------------------------------------------
    # 1. Load graphs TXT
    # ----------------------------------------------------
    G_log_txt = read_graph(cfg["logical_graph"])
    G_phys_txt = read_graph(cfg["physical_graph"])

    # ----------------------------------------------------
    # 2. Load JSON (per plotting)
    # ----------------------------------------------------
    G_log_json, logical_metadata = read_graph_json(cfg.get("logical_graph_json"))
    G_phys_json, physical_metadata = read_graph_json(cfg.get("physical_graph_json"))

    logical_dwave = logical_metadata and logical_metadata.get("type","").lower() in ("chimera","pegasus","zephyr")
    physical_dwave = physical_metadata and physical_metadata.get("type","").lower() in ("chimera","pegasus","zephyr")

    timeout = cfg.get("timeout_seconds", None)
    allow_shared = cfg.get("allow_shared_physical_qubits", False)
    check_treewidth = cfg.get("check_treewidth", False)
    reduce_physical_file = cfg.get("reduce_physical_graph", None)

    # ----------------------------------------------------
    # 3. CNF GENERATOR
    # ----------------------------------------------------
    t0 = time.time()
    gen = CNFGenerator(
        G_log=G_log_txt,
        G_phys=G_phys_txt,
        G_log_json=G_log_json,
        G_phys_json=G_phys_json,
        allow_shared_physical=allow_shared,
        exp_dir=exp_dir,
        exp_id=exp_id,
        check_treewidth=check_treewidth,
        skip_reduction=skip_reduction      
    )

    # Precheck: non embeddable
    if not gen.embeddable:
        print("[ERROR] Embedding impossibile — salto solver.")
        
        # Chiede all'utente se visualizzare le etichette
        show_labels_choice = input("\nVuoi visualizzare le etichette nei grafici? (si/no): ").strip().lower()
        show_labels = (show_labels_choice == "si")
        
        write_experiment_output(
            exp_id, cfg, G_log_txt, G_phys_txt,
            0, 0, "pairwise",
            "none",
            time.time() - t0, 0.0,
            "PRUNED",
            solution=None,
            unsat_clauses=None,
            solver_error="Embedding prechecked as impossible",
            output_dir=exp_dir
        )
        plot_noembedding(
            G_log_json, G_phys_json, exp_dir, exp_id,
            logical_metadata=logical_metadata,
            physical_metadata=physical_metadata,
            logical_dwave=logical_dwave,
            physical_dwave=physical_dwave,
            show_labels=show_labels
        )
        return

    num_vars, num_clauses = gen.generate()

    dimacs_path = os.path.join(exp_dir, f"exp_{exp_id}_{variant}.cnf")
    gen.write_dimacs(dimacs_path)
    t1 = time.time()

    # ----------------------------------------------------
    # 4. ENUMERAZIONE SOLUZIONI SAT
    # ----------------------------------------------------
    # Chiede all'utente se recuperare tutte le soluzioni
    user_choice = input("\nVuoi recuperare tutte le soluzioni? (si/no): ").strip().lower()
    enumerate_all = (user_choice == "si")

    # Chiede all'utente se visualizzare le etichette
    show_labels_choice = input("\nVuoi visualizzare le etichette nei grafici? (si/no): ").strip().lower()
    show_labels = (show_labels_choice == "si")

    all_solutions = []
    solution_map = None
    unsat_clauses_serializable = None

    while True:
        t_sat_start = time.time()
        res = solve_dimacs_file(dimacs_path, timeout_seconds=timeout, cnf_gen=gen)
        t_sat_end = time.time()
        elapsed_sat = t_sat_end - t_sat_start
        
        if res.get("status") == "UNSAT":
            core_ids = res.get("unsat_core")
            if core_ids:
                # invert mapping var_id -> (logical_id, physical_id)
                rev_var_map = {vid: (i, a) for (i, a), vid in gen.var_map.items()}

                def clause_to_struct(clause, ctype):
                    logicals = []
                    physicals = []
                    for lit in clause:
                        vid = abs(lit)
                        entry = rev_var_map.get(vid)
                        if entry:
                            i, a = entry
                            logicals.append(i)
                            physicals.append(a)
                    return {
                        "type": ctype,
                        "clause": clause,
                        "logical_pair": logicals,
                        "physical_pair": physicals,
                    }

                unsat_clauses_serializable = []
                for cid in core_ids:
                    clause = gen.clauses[cid]
                    ctype = gen.clause_type[cid] if cid < len(gen.clause_type) else "unknown"
                    unsat_clauses_serializable.append(clause_to_struct(clause, ctype))
            else:
                unsat_clauses_serializable = None
        if not res.get("model"):
            print("[INFO] Nessuna soluzione trovata.")
            break
        if res.get("status") != "SAT" or not res.get("model"):
            print("[INFO] Nessun'altra soluzione trovata.")
            break

        rev = {vid: (i, a) for (i, a), vid in gen.var_map.items()}
        solution_map = {
            i: a
            for lit in res["model"] if lit > 0
            for entry in [rev.get(lit)]
            if entry
            for i, a in [entry]
        }

        all_solutions.append({
            "assignment": solution_map,
            "sat_time": elapsed_sat
        })

        print(f"[INFO] Soluzione trovata ({variant}): {solution_map}")

        if not enumerate_all:
            break

        # Clausola di esclusione
        exclude_clause = [-gen.var_map[(i, a)] for i, a in solution_map.items()]
        gen.clauses.append(exclude_clause)
        gen.clause_type.append("EXCLUDE_PREVIOUS")
        gen.write_dimacs(dimacs_path)

    # ----------------------------------------------------
    # 5. Scrittura JSON finale
    # ----------------------------------------------------
    total_sat_time = sum(sol["sat_time"] for sol in all_solutions)
    final_status = "SAT" if all_solutions else res.get("status", "UNKNOWN")
    

    
    write_experiment_output(
        exp_id, cfg, G_log_txt, G_phys_txt,
        num_vars, num_clauses, "pairwise",
        "glucose",
        t1 - t0,
        total_sat_time,
        final_status,
        solution=all_solutions,
        solver_error=res.get("error"),
        unsat_clauses=unsat_clauses_serializable,
        output_dir=exp_dir
    )


    print(f"[INFO] Saved results in: {exp_dir}")

    # ----------------------------------------------------
    # 6. Plot embedding
    # ----------------------------------------------------
    if all_solutions:
        best_solution = all_solutions[0]["assignment"]
        plot_embedding(
            G_log_json, G_phys_json,
            best_solution, exp_dir, exp_id,
            reduced_file=reduce_physical_file,
            logical_metadata=logical_metadata,
            physical_metadata=physical_metadata,
            logical_dwave=logical_dwave,
            physical_dwave=physical_dwave,
            show_labels=show_labels
        )
    else:
        plot_noembedding(
            G_log_json, G_phys_json, exp_dir, exp_id,
            reduced_file=reduce_physical_file,
            logical_metadata=logical_metadata,
            physical_metadata=physical_metadata,
            logical_dwave=logical_dwave,
            physical_dwave=physical_dwave,
            show_labels=show_labels
        )



# ======================================================================
#  ENTRY POINT
# ======================================================================
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg_all = yaml.safe_load(f)

    ensure_dir("outputs")

    for cfg in cfg_all.get("experiments", []):
        
        # Caso normale → solo CNF ridotta
        if not cfg.get("generate_full_and_reduced", False):
            cfg["variant"] = "reduced"
            run_experiment(cfg, skip_reduction=False)
            continue

        # Caso speciale: full + reduced
        print(f"\n[INFO] Esperimento {cfg['id']} → FULL + REDUCED")

        cfg_reduced = dict(cfg)
        cfg_full = dict(cfg)

        cfg_reduced["variant"] = "reduced"
        cfg_full["variant"] = "full"

        print("\n========== VARIANTE RIDOTTA ==========")
        run_experiment(cfg_reduced, skip_reduction=False)

        print("\n========== VARIANTE FULL ==========")
        run_experiment(cfg_full, skip_reduction=True)
