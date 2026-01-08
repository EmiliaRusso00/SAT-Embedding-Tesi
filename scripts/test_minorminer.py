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

    # nodi
    for n in data["nodes"]:
        if isinstance(n, list) and len(n) == 2 and isinstance(n[1], dict):
            G.add_node(n[0], **n[1])
        else:
            G.add_node(tuple(n) if isinstance(n, list) else n)

    # archi
    for u, v in data["edges"]:
        u = tuple(u) if isinstance(u, list) else u
        v = tuple(v) if isinstance(v, list) else v
        G.add_edge(u, v)

    if "metadata" in data:
        G.graph.update(data["metadata"])

    return G

# ---------------------------------------------------------
# ESTRAZIONE ARCHI FISICI USATI (CORRETTA)
# ---------------------------------------------------------
def compute_used_physical_edges(G_logical, G_physical, embedding):
    """
    Restituisce:
    - physical_edges_logical: archi fisici che implementano archi logici
    - physical_edges_chain: archi fisici interni alle catene
    """
    physical_edges_logical = set()
    physical_edges_chain = set()

    # --- archi fisici che realizzano archi logici ---
    for u, v in G_logical.edges():
        if u not in embedding or v not in embedding:
            continue

        for pu in embedding[u]:
            for pv in embedding[v]:
                if G_physical.has_edge(pu, pv):
                    physical_edges_logical.add(tuple(sorted((pu, pv))))

    # --- archi fisici interni alle catene (chain edges) ---
    for _, chain in embedding.items():
        chain = list(chain)
        for i in range(len(chain)):
            for j in range(i + 1, len(chain)):
                if G_physical.has_edge(chain[i], chain[j]):
                    physical_edges_chain.add(
                        tuple(sorted((chain[i], chain[j])))
                    )

    return physical_edges_logical, physical_edges_chain

# ---------------------------------------------------------
# RUN MINORMINER (FULL o REDUCED)
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
    out_path = os.path.join(out_dir, "minorminer_result.json")

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(
        f"[ MM | {mode.upper()} ] Successo: {result['success']} | "
        f"Tempo: {elapsed:.4f}s | "
        f"Max chain: {result['max_chain_length']} | "
        f"Archi logici fisici: {len(result['physical_edges_logical'])} | "
        f"Archi chain: {len(result['physical_edges_chain'])}"
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

    print("\n=== AVVIO ESPERIMENTI MINORMINER ===")

    summary = []

    for exp in experiments:
        exp_id = exp["id"]
        print(f"\n=== ESPERIMENTO {exp_id} ===")

        G_logical = load_graph_json(exp["logical_graph_json"])

        # ---------- FULL ----------
        G_physical_full = load_graph_json(exp["physical_graph_json"])
        full_dir = os.path.join(output_base, str(exp_id), "full")
        summary.append(
            run_minorminer(G_logical, G_physical_full, exp, "full", full_dir)
        )

        # ---------- REDUCED ----------
        reduced_path = exp.get("reduce_physical_graph")
        if reduced_path and os.path.isfile(reduced_path):
            G_physical_reduce = load_graph_json(reduced_path)
            reduce_dir = os.path.join(output_base, str(exp_id), "reduced")
            summary.append(
                run_minorminer(G_logical, G_physical_reduce, exp, "reduced", reduce_dir)
            )
        else:
            print(f"[ MM | REDUCE ] File ridotto non trovato per esperimento {exp_id}")

    summary_path = os.path.join(output_base, "minorminer_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== COMPLETATO ===")
    print(f"Riepilogo salvato in {summary_path}")

if __name__ == "__main__":
    main()
