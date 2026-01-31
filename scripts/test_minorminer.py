import json
import time
import yaml
import os
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
                    physical_edges_chain.add(
                        tuple(sorted((chain[i], chain[j])))
                    )

    return physical_edges_logical, physical_edges_chain

# ---------------------------------------------------------
# RUN MINORMINER
# ---------------------------------------------------------
def run_minorminer(G_logical, G_physical, exp, mode, out_dir):
    print(f"[ MM | {mode.upper()} ] Avvio")

    start = time.perf_counter()

    embedding = minorminer.find_embedding(
        G_logical.edges(),
        G_physical.edges(),
        timeout=exp.get("timeout_seconds", 30)
    )

    elapsed = time.perf_counter() - start

    result = {
        "experiment_id": exp["id"],
        "mode": mode,
        "success": bool(embedding),
        "time_seconds": elapsed,
        "num_logical_nodes": G_logical.number_of_nodes(),
        "num_physical_nodes": G_physical.number_of_nodes(),
        "embedding": {},
        "max_chain_length": None,
        "avg_chain_length": None,
        "physical_edges_logical": [],
        "physical_edges_chain": []
    }

    if embedding:
        chains = list(embedding.values())
        lengths = [len(c) for c in chains]

        result["embedding"] = {str(k): list(v) for k, v in embedding.items()}
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

    print(
        f"[ MM | {mode.upper()} ] Successo: {result['success']} | "
        f"Tempo: {elapsed:.4f}s | "
        f"Max chain: {result['max_chain_length']}"
    )

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

        full_attempts_to_1to1 = None
        reduced_attempts_to_1to1 = None

        full_times = []
        reduced_times = []

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
                    G_logical,
                    G_physical_full,
                    exp,
                    "full",
                    os.path.join(output_base, str(exp_id), "full")
                )

                full_times.append(res["time_seconds"])

                if res["success"] and res["max_chain_length"] == 1:
                    if full_first_success is None:
                        full_first_success = res
                        full_attempts_to_1to1 = full_attempts
                    full_done = True

            # -------- REDUCED --------
            if G_physical_reduce and not reduced_done:
                reduced_attempts += 1
                res = run_minorminer(
                    G_logical,
                    G_physical_reduce,
                    exp,
                    "reduced",
                    os.path.join(output_base, str(exp_id), "reduced")
                )

                reduced_times.append(res["time_seconds"])

                if res["success"] and res["max_chain_length"] == 1:
                    if reduced_first_success is None:
                        reduced_first_success = res
                        reduced_attempts_to_1to1 = reduced_attempts
                    reduced_done = True

            if G_physical_reduce is None:
                reduced_done = True

        summary.append({
            "experiment_id": exp_id,

            "full": {
                "total_attempts": full_attempts,
                "found_1to1": bool(full_first_success),
                "attempts_to_first_1to1": full_attempts_to_1to1,
                "first_success_time": (
                    full_first_success["time_seconds"]
                    if full_first_success else None
                ),
                "avg_attempt_time": (
                    sum(full_times) / len(full_times)
                    if full_times else None
                )
            },

            "reduced": {
                "total_attempts": reduced_attempts,
                "found_1to1": bool(reduced_first_success),
                "attempts_to_first_1to1": reduced_attempts_to_1to1,
                "first_success_time": (
                    reduced_first_success["time_seconds"]
                    if reduced_first_success else None
                ),
                "avg_attempt_time": (
                    sum(reduced_times) / len(reduced_times)
                    if reduced_times else None
                )
            },

            "attempts_loop": iter_count,
            "max_attempts_allowed": max_attempts
        })

    os.makedirs(output_base, exist_ok=True)
    with open(os.path.join(output_base, "minorminer_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== COMPLETATO ===")

if __name__ == "__main__":
    main()
