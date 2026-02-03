import json
import time
import yaml
import os
import copy
import networkx as nx
import minorminer

# ---------------------------------------------------------
# CARICATORE GRAFO JSON
# ---------------------------------------------------------
def load_graph_json(path):
    with open(path, "r") as f:
        data = json.load(f)

    G = nx.Graph()

    for n in data["nodes"]:
        if isinstance(n, list) and len(n) == 2 and isinstance(n[1], dict):
            G.add_node(n[0], **n[1])
        else:
            G.add_node(tuple(n) if isinstance(n, list) else n)

    for u, v in data["edges"]:
        u = tuple(u) if isinstance(u, list) else u
        v = tuple(v) if isinstance(v, list) else v
        G.add_edge(u, v)

    if "metadata" in data:
        G.graph.update(data["metadata"])

    return G

# ---------------------------------------------------------
# ESTRAZIONE ARCHI FISICI USATI
# ---------------------------------------------------------
def compute_used_physical_edges(G_logical, G_physical, embedding):
    physical_edges_logical = set()
    physical_edges_chain = set()

    for u, v in G_logical.edges():
        if u not in embedding or v not in embedding:
            continue
        for pu in embedding[u]:
            for pv in embedding[v]:
                if G_physical.has_edge(pu, pv):
                    physical_edges_logical.add(tuple(sorted((pu, pv))))

    for chain in embedding.values():
        chain = list(chain)
        for i in range(len(chain)):
            for j in range(i + 1, len(chain)):
                if G_physical.has_edge(chain[i], chain[j]):
                    physical_edges_chain.add(tuple(sorted((chain[i], chain[j]))))

    return physical_edges_logical, physical_edges_chain

# ---------------------------------------------------------
# CHECK ARCHI LOGICI
# ---------------------------------------------------------
def respects_logical_edges(G_logical, embedding, G_physical):
    for u, v in G_logical.edges():
        if u not in embedding or v not in embedding:
            return False
        if not any(G_physical.has_edge(a, b) for a in embedding[u] for b in embedding[v]):
            return False
    return True

# ---------------------------------------------------------
# CONFRONTO EMBEDDING
# ---------------------------------------------------------
def better_embedding(a, b):
    if not a["success"]:
        return False
    if b is None:
        return True
    # 1) minimo numero di nodi fisici usati
    if a["num_physical_used"] != b["num_physical_used"]:
        return a["num_physical_used"] < b["num_physical_used"]
    # 2) minima chain massima
    if a["max_chain_length"] != b["max_chain_length"]:
        return a["max_chain_length"] < b["max_chain_length"]
    # 3) minima chain media
    if a["avg_chain_length"] != b["avg_chain_length"]:
        return a["avg_chain_length"] < b["avg_chain_length"]
    # 4) minimo tempo
    return a["time_seconds"] < b["time_seconds"]

# ---------------------------------------------------------
# RUN MINORMINER
# ---------------------------------------------------------
def run_minorminer(G_logical, G_physical, exp, mode, out_dir, attempt, max_attempts):
    start = time.perf_counter()

    embedding = minorminer.find_embedding(
        G_logical.edges(),
        G_physical.edges(),
        timeout=exp.get("timeout_seconds", 30)
    )

    elapsed = time.perf_counter() - start

    success = bool(embedding) and respects_logical_edges(G_logical, embedding, G_physical)

    # --- Messaggio tentativo ---
    attempt_str = f"{attempt}/{max_attempts}"
    if success:
        print(f"[ MM Success {attempt_str} | {mode.upper()} ] "
              f"Successo: {success} | Tempo: {elapsed:.4f}s | "
              f"Max chain: {max(len(c) for c in embedding.values())} | "
              f"Num fisici usati: {len(set().union(*embedding.values()))}")
    else:
        print(f"[ MM Fail {attempt_str} | {mode.upper()} ] "
              f"Avviso: l'embedding non rispetta tutti gli archi logici.")

    result = {
        "experiment_id": exp["id"],
        "mode": mode,
        "success": success,
        "time_seconds": elapsed,
        "num_logical_nodes": G_logical.number_of_nodes(),
        "num_physical_nodes": G_physical.number_of_nodes(),
        "num_physical_used": None,
        "embedding": {},
        "max_chain_length": None,
        "avg_chain_length": None,
        "physical_edges_logical": [],
        "physical_edges_chain": []
    }

    if embedding:
        used_physical_nodes = set()
        for chain in embedding.values():
            used_physical_nodes.update(chain)

        chains = list(embedding.values())
        lengths = [len(c) for c in chains]

        result["embedding"] = {str(k): list(v) for k, v in embedding.items()}
        result["num_physical_used"] = len(used_physical_nodes)
        result["max_chain_length"] = max(lengths)
        result["avg_chain_length"] = sum(lengths) / len(lengths)

        logical_edges, chain_edges = compute_used_physical_edges(
            G_logical, G_physical, embedding
        )
        result["physical_edges_logical"] = list(logical_edges)
        result["physical_edges_chain"] = list(chain_edges)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "minorminer_result.json"), "w") as f:
        json.dump(result, f, indent=2)

    return result

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    experiments = config["experiments"]
    output_base = config.get("output_dir", "outputs")

    summary = []

    for exp in experiments:
        exp_id = exp["id"]
        print(f"\n=== ESPERIMENTO {exp_id} ===")

        G_logical = load_graph_json(exp["logical_graph_json"])
        G_physical_full = load_graph_json(exp["physical_graph_json"])

        reduced_path = exp.get("reduce_physical_graph")
        G_physical_reduce = (
            load_graph_json(reduced_path)
            if reduced_path and os.path.isfile(reduced_path)
            else None
        )

        max_attempts = exp.get("max_attempts", 100)

        full_attempts = 0
        reduced_attempts = 0

        full_time_accum = 0.0
        reduced_time_accum = 0.0
        best_full = None
        best_reduced = None
        full_first_success = None
        reduced_first_success = None

        full_done = False
        reduced_done = False
        iter_count = 0

        while (not full_done or not reduced_done) and iter_count < max_attempts:
            iter_count += 1

            # -------- FULL --------
            if not full_done:
                full_attempts += 1
                res = run_minorminer(
                    G_logical, G_physical_full, exp, "full",
                    os.path.join(output_base, str(exp_id), "full"),
                    attempt=full_attempts, max_attempts=max_attempts
                )
                full_time_accum += res["time_seconds"]

                if res["success"] and better_embedding(res, best_full):
                    best_full = copy.deepcopy(res)
                if res["success"] and res["max_chain_length"] == 1:
                    full_first_success = copy.deepcopy(res)

                    full_first_success["time_to_1to1"] = full_time_accum
                    full_first_success["time_single_run_1to1"] = res["time_seconds"]
                    full_first_success["attempts_to_1to1"] = full_attempts
                    full_done = True

            # -------- REDUCED --------
            if G_physical_reduce and not reduced_done:
                reduced_attempts += 1
                res = run_minorminer(
                    G_logical, G_physical_reduce, exp, "reduced",
                    os.path.join(output_base, str(exp_id), "reduced"),
                    attempt=reduced_attempts, max_attempts=max_attempts
                )
                reduced_time_accum += res["time_seconds"]
                if res["success"] and better_embedding(res, best_reduced):
                    best_reduced = copy.deepcopy(res)
                if res["success"] and res["max_chain_length"] == 1:
                    reduced_first_success = copy.deepcopy(res)

                    reduced_first_success["time_to_1to1"] = reduced_time_accum
                    reduced_first_success["time_single_run_1to1"] = res["time_seconds"]
                    reduced_first_success["attempts_to_1to1"] = reduced_attempts
                    reduced_done = True
            if G_physical_reduce is None:
                reduced_done = True

        # --- Salva il miglior embedding ---
        final_full = full_first_success if full_first_success else best_full
        if final_full:
            out_dir_full = os.path.join(output_base, str(exp_id), "full")
            os.makedirs(out_dir_full, exist_ok=True)
            with open(os.path.join(out_dir_full, "minorminer_result.json"), "w") as f_full:
                json.dump(final_full, f_full, indent=2)

        if G_physical_reduce:
            final_reduced = reduced_first_success if reduced_first_success else best_reduced
            if final_reduced:
                out_dir_reduced = os.path.join(output_base, str(exp_id), "reduced")
                os.makedirs(out_dir_reduced, exist_ok=True)
                with open(os.path.join(out_dir_reduced, "minorminer_result.json"), "w") as f_red:
                    json.dump(final_reduced, f_red, indent=2)

        summary.append({
            "experiment_id": exp_id,
            "full": {
                "total_attempts": full_attempts,
                "found_1to1": bool(full_first_success),
                "best_embedding": final_full
            },
            "reduced": {
                "total_attempts": reduced_attempts,
                "found_1to1": bool(reduced_first_success),
                "best_embedding": final_reduced if G_physical_reduce else None
            }
        })

    os.makedirs(output_base, exist_ok=True)
    with open(os.path.join(output_base, "minorminer_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== COMPLETATO ===")


if __name__ == "__main__":
    main()
