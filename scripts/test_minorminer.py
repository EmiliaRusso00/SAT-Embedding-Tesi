import json
import time
import yaml
import os
import networkx as nx
import minorminer

# ---------------------------------------------------------
# NORMALIZZAZIONE NODI
# ---------------------------------------------------------
def normalize_node(n):
    if isinstance(n, tuple):
        return n
    if isinstance(n, list):
        return tuple(n)
    return (n,)

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
            # nodo con attributi
            G.add_node(n[0], **n[1])
        else:
            # nodo semplice (tuple, int, string)
            G.add_node(tuple(n) if isinstance(n, list) else n)


    # archi
    for u, v in data["edges"]:
        u = tuple(u) if isinstance(u, list) else u
        v = tuple(v) if isinstance(v, list) else v
        G.add_edge(u, v)

    # metadata opzionale
    if "metadata" in data:
        G.graph.update(data["metadata"])

    return G

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
        "used_edges": []
    }

    if embedding:
        chains = list(embedding.values())
        lengths = [len(c) for c in chains]

        result["embedding"] = {str(k): list(v) for k, v in embedding.items()}
        result["max_chain_length"] = max(lengths)
        result["avg_chain_length"] = sum(lengths) / len(lengths)

        used_edges = set()
        for u, v in G_logical.edges():
            if u in embedding and v in embedding:
                u_phys = normalize_node(list(embedding[u])[0])
                v_phys = normalize_node(list(embedding[v])[0])
                used_edges.add(tuple(sorted((u_phys, v_phys))))

        result["used_edges"] = list(used_edges)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "minorminer_result.json")

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(
        f"[ MM | {mode.upper()} ] Successo: {result['success']} | "
        f"Tempo: {elapsed:.4f}s | "
        f"Max chain: {result['max_chain_length']} | "
        f"Archi usati: {len(result['used_edges'])}"
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

        # carica grafo logico
        G_logical = load_graph_json(exp["logical_graph_json"])

        # ---------- FULL ----------
        G_physical_full = load_graph_json(exp["physical_graph_json"])
        full_dir = os.path.join(output_base, str(exp_id), "full")
        res_full = run_minorminer(G_logical, G_physical_full, exp, "full", full_dir)
        summary.append(res_full)

        # ---------- REDUCED ----------
        reduced_path = exp.get("reduce_physical_graph")
        if reduced_path and os.path.isfile(reduced_path):
            G_physical_reduce = load_graph_json(reduced_path)
            reduce_dir = os.path.join(output_base, str(exp_id), "reduced")
            res_reduce = run_minorminer(G_logical, G_physical_reduce, exp, "reduced", reduce_dir)
            summary.append(res_reduce)
        else:
            print(f"[ MM | REDUCE ] File ridotto non trovato per esperimento {exp_id}")

    # Salva riepilogo globale
    summary_path = os.path.join(output_base, "minorminer_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== COMPLETATO ===")
    print(f"Riepilogo salvato in {summary_path}")


if __name__ == "__main__":
    main()
