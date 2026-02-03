import argparse
import time
import yaml
import os
import networkx as nx

from parser import read_graph, read_graph_json
from cnf_generator_incremental import CNFGenerator
from solver_interface import solve_dimacs_file
from metrics import write_experiment_output
from utils import ensure_dir
from plot_utils import plot_embedding, plot_noembedding

# ============================================================
# Funzioni ausiliarie
# ============================================================

def compute_incremental_subgraphs(G_log):
    # 1) k-core massimo
    core_number = nx.core_number(G_log)
    k_max = max(core_number.values())
    dense_core_nodes = [n for n, k in core_number.items() if k == k_max]

    # 2) distanza minima da QUALSIASI nodo del core
    distances = {
        n: min(
            nx.shortest_path_length(G_log, source=c, target=n)
            for c in dense_core_nodes
        )
        for n in G_log.nodes()
    }

    max_distance = max(distances.values())
    incremental_subgraphs = []

    # 3) crescita per layer di distanza
    for d in range(max_distance + 1):
        nodes_in_subgraph = [n for n, dist in distances.items() if dist <= d]
        subgraph = G_log.subgraph(nodes_in_subgraph).copy()
        incremental_subgraphs.append(subgraph)

    return incremental_subgraphs


# ============================================================
# Funzione principale per un esperimento
# ============================================================

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
    # VARIANTE 2: REDUCED GRAPH INCREMENTALE CON EREDITA'
    # ============================================================
    print("\n========== VARIANTE 2: REDUCED GRAPH INCREMENTALE ==========")
    variant_reduced = "reduced"
    exp_dir_reduced = os.path.join(exp_dir_base, variant_reduced)
    ensure_dir(exp_dir_reduced)

    incremental_subgraphs = compute_incremental_subgraphs(G_log_txt)
    all_step_results = []

    forced_assignments = {}  # dizionario cumulativo tra step

    for step, G_sub in enumerate(incremental_subgraphs):
        print(f"\n[INFO] Step {step}: sotto-grafo con {len(G_sub.nodes())} nodi")
        logical_center = nx.center(G_sub)[0]
        min_deg_required = G_sub.degree(logical_center)

        centers_phys_all = nx.center(G_phys_txt)
        candidate_centers = [c for c in centers_phys_all if G_phys_txt.degree(c) >= min_deg_required]
        if not candidate_centers:
            print("[ERROR] Nessun centro fisico valido.")
            continue

        step_solution = None
        time_cnf_step = 0.0
        sat_time_step = 0.0
        num_vars_step = 0
        num_clauses_step = 0

        for center_node in candidate_centers:
            print(f"[INFO] Tentativo con centro fisico: {center_node}")
            gen = CNFGenerator(
                G_log=G_sub,
                G_phys=G_phys_txt,
                G_log_json=G_log_json,
                G_phys_json=G_phys_json,
                exp_dir=exp_dir_reduced,
                exp_id=f"{exp_id}_step{step}",
                skip_reduction=False,
                physical_center=center_node,
                forced_assignments=forced_assignments  # <-- eredita qui
            )
            reduced_file = os.path.join(exp_dir_reduced, f"reduced_physical_{exp_id}_step{step}.json")

            if not gen.embeddable:
                continue

            t_cnf_start = time.time()
            num_vars_step, num_clauses_step = gen.generate()
            t_cnf_end = time.time()
            time_cnf_step = t_cnf_end - t_cnf_start

            dimacs_path = os.path.join(exp_dir_reduced, f"exp_{exp_id}_step{step}.cnf")
            gen.write_dimacs(dimacs_path)

            t_sat_start = time.time()
            res = solve_dimacs_file(dimacs_path, timeout_seconds=timeout, cnf_gen=gen)
            t_sat_end = time.time()
            sat_time_step = t_sat_end - t_sat_start

            if res.get("status") == "SAT" and res.get("model"):
                rev = {vid: (i, a) for (i, a), vid in gen.var_map.items()}
                step_solution = {
                    i: a for lit in res["model"] if lit > 0
                    for entry in [rev.get(lit)] if entry
                    for i, a in [entry]
                }
                forced_assignments.update(step_solution)  # <-- aggiorna cumulativo
                print(f"[SUCCESS] SAT trovato allo step {step} con centro fisico {center_node}")
                break

        all_step_results.append({
            "step": step,
            "num_nodes": len(G_sub.nodes()),
            "num_vars": num_vars_step,
            "num_clauses": num_clauses_step,
            "time_cnf": time_cnf_step,
            "time_sat": sat_time_step,
            "solution": step_solution,
            "reduced_file": reduced_file
        })

    # --- Salvataggio risultati e plot ---
    for res in all_step_results:
        step_dir = os.path.join(exp_dir_reduced, f"step_{res['step']}")
        ensure_dir(step_dir)

        write_experiment_output(
            exp_id, cfg, G_log_txt, G_phys_txt,
            res["num_vars"], res["num_clauses"], "pairwise",
            "glucose", res["time_cnf"], res["time_sat"],
            "SAT" if res["solution"] else "UNSAT",
            solution=[{"assignment": res["solution"]}] if res["solution"] else None,
            output_dir=step_dir
        )

        if res["solution"]:
            plot_embedding(
                G_log_json, G_phys_json,
                res["solution"], step_dir, exp_id,
                reduced_file=res["reduced_file"],
                logical_metadata=logical_metadata,
                physical_metadata=physical_metadata,
                logical_dwave=logical_dwave,
                physical_dwave=physical_dwave,
                show_labels=True,
                mode=variant_reduced
            )
        else:
            plot_noembedding(
                G_log_json, G_phys_json, step_dir, exp_id,
                reduced_file=res["reduced_file"],
                logical_metadata=logical_metadata,
                physical_metadata=physical_metadata,
                logical_dwave=logical_dwave,
                physical_dwave=physical_dwave,
                show_labels=True
            )

    print("[INFO] Esperimento ridotto completato.")

    # ============================================================
    # VARIANTE 1: FULL GRAPH INCREMENTALE SENZA CENTRO FISICO
    # ============================================================
    print("\n========== VARIANTE 1: FULL GRAPH INCREMENTALE ==========")
    variant_full = "full"
    exp_dir_full = os.path.join(exp_dir_base, variant_full)
    ensure_dir(exp_dir_full)

    incremental_subgraphs_full = compute_incremental_subgraphs(G_log_txt)
    all_step_results_full = []

    # forced_assignments parte vuoto 
    forced_assignments_full = {}

    for step, G_sub in enumerate(incremental_subgraphs_full):
        print(f"\n[INFO] Step {step} FULL GRAPH: sotto-grafo con {len(G_sub.nodes())} nodi")

        step_solution = None
        time_cnf_step = 0.0
        sat_time_step = 0.0
        num_vars_step = 0
        num_clauses_step = 0

        # Creiamo il CNFGenerator senza specificare centro fisico
        gen = CNFGenerator(
            G_log=G_sub,
            G_phys=G_phys_txt,
            G_log_json=G_log_json,
            G_phys_json=G_phys_json,
            exp_dir=exp_dir_full,
            exp_id=f"{exp_id}_full_step{step}",
            skip_reduction=True,
            forced_assignments=forced_assignments_full  # eredita dai passi precedenti
        )

        if not gen.embeddable:
            print("[WARN] Step non embeddibile, salto questo sotto-grafo")
            continue

        # --- CNF generation ---
        t_cnf_start = time.time()
        num_vars_step, num_clauses_step = gen.generate()
        t_cnf_end = time.time()
        time_cnf_step = t_cnf_end - t_cnf_start

        # --- Scrittura DIMACS ---
        dimacs_path = os.path.join(exp_dir_full, f"exp_{exp_id}_full_step{step}.cnf")
        gen.write_dimacs(dimacs_path)

        # --- SAT solving ---
        t_sat_start = time.time()
        res = solve_dimacs_file(dimacs_path, timeout_seconds=timeout, cnf_gen=gen)
        t_sat_end = time.time()
        sat_time_step = t_sat_end - t_sat_start

        if res.get("status") == "SAT" and res.get("model"):
            rev = {vid: (i, a) for (i, a), vid in gen.var_map.items()}
            step_solution = {
                i: a for lit in res["model"] if lit > 0
                for entry in [rev.get(lit)] if entry
                for i, a in [entry]
            }
            forced_assignments_full.update(step_solution)
            print(f"[SUCCESS] SAT trovato allo step {step} FULL")

        all_step_results_full.append({
            "step": step,
            "num_nodes": len(G_sub.nodes()),
            "num_vars": num_vars_step,
            "num_clauses": num_clauses_step,
            "time_cnf": time_cnf_step,
            "time_sat": sat_time_step,
            "solution": step_solution
        })

    # --- Salvataggio risultati e plot ---
    for res in all_step_results_full:
        step_dir = os.path.join(exp_dir_full, f"step_{res['step']}")
        ensure_dir(step_dir)

        write_experiment_output(
            exp_id, cfg, G_log_txt, G_phys_txt,
            res["num_vars"], res["num_clauses"], "pairwise",
            "glucose", res["time_cnf"], res["time_sat"],
            "SAT" if res["solution"] else "UNSAT",
            solution=[{"assignment": res["solution"]}] if res["solution"] else None,
            output_dir=step_dir
        )

        if res["solution"]:
            plot_embedding(
                G_log_json, G_phys_json,
                res["solution"], step_dir, exp_id,
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
                G_log_json, G_phys_json, step_dir, exp_id,
                reduced_file=None,
                logical_metadata=logical_metadata,
                physical_metadata=physical_metadata,
                logical_dwave=logical_dwave,
                physical_dwave=physical_dwave,
                show_labels=True
            )

    print("[INFO] Esperimento FULL incrementale completato.")


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg_all = yaml.safe_load(f)

    ensure_dir("outputs")

    for cfg in cfg_all.get("experiments", []):
        run_experiment(cfg)
