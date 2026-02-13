import argparse
import time
import yaml
import os
import networkx as nx

from parser import read_graph, read_graph_json
from cnf_generator import CNFGenerator
from solver_interface_cripto import solve_dimacs_file
from metrics import write_experiment_output
from utils import ensure_dir
from plot_utils import plot_embedding, plot_noembedding


def run_experiment(cfg):
    exp_id = cfg.get("id", 0)
    print(f"\n[INFO] Running experiment ID: {exp_id}")

    exp_dir_base = os.path.join("outputs", str(exp_id))
    ensure_dir(exp_dir_base)

    # --- Load graphs ---
    G_log_txt = read_graph(cfg["logical_graph"])
    G_phys_txt = read_graph(cfg["physical_graph"])

    G_log_json, logical_metadata = read_graph_json(cfg.get("logical_graph_json"))
    G_phys_json, physical_metadata = read_graph_json(cfg.get("physical_graph_json"))

    logical_dwave = logical_metadata and logical_metadata.get("type", "").lower() in ("chimera", "pegasus", "zephyr")
    physical_dwave = physical_metadata and physical_metadata.get("type", "").lower() in ("chimera", "pegasus", "zephyr")

    timeout = cfg.get("timeout_seconds", None)
    
    # ============================================================
    # VARIANTE 2: REDUCED GRAPH
    # ============================================================
    print("\n========== VARIANTE 2: REDUCED GRAPH ==========")
    variant_reduced = "reduced"
    exp_dir_reduced = os.path.join(exp_dir_base, variant_reduced)
    ensure_dir(exp_dir_reduced)

    logical_center = nx.center(G_log_txt)[0]
    min_deg_required = G_log_txt.degree(logical_center)

    centers_phys_all = nx.center(G_phys_txt)
    candidate_centers = [c for c in centers_phys_all if G_phys_txt.degree(c) >= min_deg_required]

    if not candidate_centers:
        print("[ERROR] Nessun centro fisico valido.")
        return

    print(f"[INFO] Centri fisici candidati: {candidate_centers}")

    # --- Chiedo all'utente se provare tutti i centri fisici ---
#   try_all = input("Vuoi provare tutti i centri fisici possibili? (y/n): ").strip().lower() == 'y'
##   if not try_all:
#        candidate_centers = [candidate_centers[0]]  # solo il primo centro

    found_solution = False
    solution_map_reduced = None
    num_vars_reduced = num_clauses_reduced = 0
    t0_reduced = time.time()
    sat_time_reduced = 0.0

    for center_node in candidate_centers:
        print(f"\n[INFO] Tentativo con centro fisico: {center_node}")

        gen = CNFGenerator(
            G_log=G_log_txt,
            G_phys=G_phys_txt,
            G_log_json=G_log_json,
            G_phys_json=G_phys_json,
            exp_dir=exp_dir_reduced,
            exp_id=exp_id,
            skip_reduction=False,
            physical_center=center_node
        )
        reduced_file = os.path.join(exp_dir_reduced, f"reduced_physical_{exp_id}.json")


        if not gen.embeddable:
            continue

        num_vars_reduced, num_clauses_reduced = gen.generate()
        dimacs_path_reduced = os.path.join(exp_dir_reduced, f"exp_{exp_id}_{variant_reduced}.cnf")
        gen.write_dimacs(dimacs_path_reduced)

        t_sat_start = time.time()
        num_threads = max(os.cpu_count() - 1, 1)
        res_reduced = solve_dimacs_file(dimacs_path_reduced, timeout_seconds=timeout, num_threads=num_threads)
        #res_reduced = solve_dimacs_file(dimacs_path_reduced, timeout_seconds=timeout, cnf_gen=gen)
        t_sat_end = time.time()
        sat_time_reduced += (t_sat_end - t_sat_start)

        if res_reduced.get("status") == "SAT" and res_reduced.get("model"):
            rev = {vid: (i, a) for (i, a), vid in gen.var_map.items()}
            solution_map_reduced = {
                i: a for lit in res_reduced["model"] if lit > 0
                for entry in [rev.get(lit)] if entry
                for i, a in [entry]
            }
            found_solution = True
            print(f"[SUCCESS] SAT con centro fisico {center_node}")
            break

    t1_reduced = time.time()
    total_time_reduced = t1_reduced - t0_reduced

    write_experiment_output(
        exp_id, cfg, G_log_txt, G_phys_txt,
        num_vars_reduced, num_clauses_reduced, "pairwise",
        "glucose", total_time_reduced, sat_time_reduced,
        "SAT" if solution_map_reduced else "UNSAT",
        solution=[{"assignment": solution_map_reduced}] if solution_map_reduced else None,
        output_dir=exp_dir_reduced
    )
    if found_solution and solution_map_reduced:
        # Se abbiamo trovato una soluzione SAT
        plot_embedding(
            G_log_json, G_phys_json,
            solution_map_reduced, exp_dir_reduced, exp_id,
            reduced_file=reduced_file,
            logical_metadata=logical_metadata,
            physical_metadata=physical_metadata,
            logical_dwave=logical_dwave,
            physical_dwave=physical_dwave,
            show_labels=True,
            mode=variant_reduced
        )
    else:
        # Se nessuna soluzione SAT trovata
        plot_noembedding(
            G_log_json, G_phys_json, exp_dir_reduced, exp_id,
            reduced_file=reduced_file,
            logical_metadata=logical_metadata,
            physical_metadata=physical_metadata,
            logical_dwave=logical_dwave,
            physical_dwave=physical_dwave,
            show_labels=True
        )



    print("[INFO] Esperimento completato.")

    # ============================================================
    # VARIANTE 1: FULL GRAPH
    # ============================================================
    print("\n========== VARIANTE 1: FULL GRAPH ==========")
    variant_full = "full"
    exp_dir_full = os.path.join(exp_dir_base, variant_full)
    ensure_dir(exp_dir_full)

    t0_full = time.time()
    sat_time_full = 0.0

    gen_full = CNFGenerator(
        G_log=G_log_txt,
        G_phys=G_phys_txt,
        G_log_json=G_log_json,
        G_phys_json=G_phys_json,
        exp_dir=exp_dir_full,
        exp_id=exp_id,
        skip_reduction=True
    )

    solution_map_full = None
    num_vars_full = num_clauses_full = 0

    if gen_full.embeddable:
        num_vars_full, num_clauses_full = gen_full.generate()
        dimacs_path_full = os.path.join(exp_dir_full, f"exp_{exp_id}_{variant_full}.cnf")
        gen_full.write_dimacs(dimacs_path_full)

        t_sat_start = time.time()
        res_full = solve_dimacs_file(dimacs_path_full, timeout_seconds=timeout, num_threads=num_threads)
        #res_full = solve_dimacs_file(dimacs_path_full, timeout_seconds=timeout, cnf_gen=gen_full)
        t_sat_end = time.time()
        sat_time_full = t_sat_end - t_sat_start

        if res_full.get("status") == "SAT" and res_full.get("model"):
            rev = {vid: (i, a) for (i, a), vid in gen_full.var_map.items()}
            solution_map_full = {
                i: a for lit in res_full["model"] if lit > 0
                for entry in [rev.get(lit)] if entry
                for i, a in [entry]
            }
            print("[SUCCESS] Soluzione SAT trovata sul grafo completo")
        else:
            print("[INFO] Nessuna soluzione SAT sul grafo completo")
    else:
        print("[ERROR] Embedding impossibile sul grafo completo")

    t1_full = time.time()
    total_time_full = t1_full - t0_full

    write_experiment_output(
        exp_id, cfg, G_log_txt, G_phys_txt,
        num_vars_full, num_clauses_full, "pairwise",
        "glucose", total_time_full, sat_time_full,
        "SAT" if solution_map_full else "UNSAT",
        solution=[{"assignment": solution_map_full}] if solution_map_full else None,
        output_dir=exp_dir_full
    )

    if solution_map_full:
        plot_embedding(
            G_log_json, G_phys_json,
            solution_map_full, exp_dir_full, exp_id,
            reduced_file=None,
            logical_metadata=logical_metadata,
            physical_metadata=physical_metadata,
            logical_dwave=logical_dwave,
            physical_dwave=physical_dwave,
            show_labels=True,
            mode=variant_full
        )
    else:
        plot_noembedding(
            G_log_json, G_phys_json, exp_dir_full, exp_id,
            reduced_file=None,
            logical_metadata=logical_metadata,
            physical_metadata=physical_metadata,
            logical_dwave=logical_dwave,
            physical_dwave=physical_dwave,
            show_labels=True
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg_all = yaml.safe_load(f)

    ensure_dir("outputs")

    for cfg in cfg_all.get("experiments", []):
        run_experiment(cfg)
