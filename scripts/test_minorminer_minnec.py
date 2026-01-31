import json 
import time
import yaml
import os
import networkx as nx
import minorminer

# ---------------------------------------------------------
# CARICA GRAFO JSON
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
# CALCOLO ARCHI USATI (LOGICI e CHAIN)
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
# MINORMINER CON 100 TENTATIVI
# ---------------------------------------------------------
def run_minorminer(G_logical, G_physical, exp, mode, out_dir):
    print(f"[ MM | {mode.upper()} ] Avvio embedding multipli (max {exp.get('max_attempts', 100)})")

    best_result = None
    best_max_chain = float('inf')
    best_physical_nodes_used = float('inf')

    max_attempts = exp.get("max_attempts", 100)
    os.makedirs(out_dir, exist_ok=True)

    for attempt in range(1, max_attempts + 1):
        start = time.perf_counter()
        embedding = minorminer.find_embedding(
            G_logical.edges(),
            G_physical.edges(),
            timeout=exp.get("timeout_seconds", 30)
        )
        elapsed = time.perf_counter() - start

        if not embedding:
            print(f"[ MM | {mode.upper()} ] Tentativo {attempt}: no embedding trovato")
            continue

        chains = list(embedding.values())
        lengths = [len(c) for c in chains]
        physical_nodes_used = len(set(n for chain in chains for n in chain))

        # confronta con migliore finora
        if max(lengths) < best_max_chain or (
            max(lengths) == best_max_chain and physical_nodes_used < best_physical_nodes_used
        ):
            logical_edges, chain_edges = compute_used_physical_edges(
                G_logical, G_physical, embedding
            )

            best_result = {
                "experiment_id": exp["id"],
                "mode": mode,
                "success": True,
                "best_attempt": attempt,
                "time_seconds": elapsed,
                "num_logical_nodes": G_logical.number_of_nodes(),
                "num_physical_nodes": G_physical.number_of_nodes(),
                "num_physical_nodes_used": physical_nodes_used,
                "embedding": {str(k): list(v) for k, v in embedding.items()},
                "max_chain_length": max(lengths),
                "avg_chain_length": sum(lengths) / len(lengths),
                "physical_edges_logical": list(logical_edges),
                "physical_edges_chain": list(chain_edges),
            }
            best_max_chain = max(lengths)
            best_physical_nodes_used = physical_nodes_used

            print(
                f"[ MM | {mode.upper()} ] Nuovo best (tentativo {attempt}): "
                f"max_chain={best_max_chain}, nodes_used={best_physical_nodes_used}"
            )

    # se nessun embedding valido trovato
    if not best_result:
        best_result = {
            "experiment_id": exp["id"],
            "mode": mode,
            "success": False,
            "best_attempt": None,
            "time_seconds": None,
            "num_logical_nodes": G_logical.number_of_nodes(),
            "num_physical_nodes": G_physical.number_of_nodes(),
            "num_physical_nodes_used": None,
            "embedding": {},
            "max_chain_length": None,
            "avg_chain_length": None,
            "physical_edges_logical": [],
            "physical_edges_chain": [],
        }

    filename = os.path.join(out_dir, "minorminer_min_nodiechain.json")
    with open(filename, "w") as f:
        json.dump(best_result, f, indent=2)

    print(
        f"[ MM | {mode.upper()} ] Report finale: "
        f"success={best_result['success']} | "
        f"max_chain={best_result['max_chain_length']} | "
        f"nodes_used={best_result['num_physical_nodes_used']}"
    )
    return best_result

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

        # cartelle output per full / reduced
        out_full = os.path.join(output_base, str(exp_id), "full")
        out_reduced = os.path.join(output_base, str(exp_id), "reduced")

        print("\n*** FULL GRAPH ***")
        best_full = run_minorminer(
            G_logical,
            G_physical_full,
            exp,
            "full",
            out_full
        )

        best_reduced = None
        if G_physical_reduce:
            print("\n*** REDUCED GRAPH ***")
            best_reduced = run_minorminer(
                G_logical,
                G_physical_reduce,
                exp,
                "reduced",
                out_reduced
            )

        summary.append({
            "experiment_id": exp_id,
            "best_full": best_full,
            "best_reduced": best_reduced,
        })

    os.makedirs(output_base, exist_ok=True)
    with open(os.path.join(output_base, "minorminer_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== COMPLETATO ===")

if __name__ == "__main__":
    main()
