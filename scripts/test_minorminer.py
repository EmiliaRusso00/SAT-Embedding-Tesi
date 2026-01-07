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
# CARICATORE GRAFO JSON DEFINITIVO
# ---------------------------------------------------------
def load_graph_json(path):
    """
    Carica grafo JSON esportato da NetworkX/D-Wave.
    Gestisce:
      - nodi semplici (int, string, tuple)
      - nodi con attributi [node, dict]
    """
    with open(path, 'r') as f:
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
    for e in data["edges"]:
        if isinstance(e, list) and len(e) == 3:
            G.add_edge(e[0], e[1], **e[2])
        else:
            u = tuple(e[0]) if isinstance(e[0], list) else e[0]
            v = tuple(e[1]) if isinstance(e[1], list) else e[1]
            G.add_edge(u, v)

    # attributi globali
    if "graph_attributes" in data:
        G.graph.update(data["graph_attributes"])

    return G

# ---------------------------------------------------------
# ESECUZIONE MINORMINER SU UN ESPERIMENTO
# ---------------------------------------------------------
def run_minorminer_experiment(exp, output_base):
    logical_path = exp["logical_graph_json"]
    physical_path = exp["physical_graph_json"]
    exp_id = exp["id"]

    print(f"\n[ MM ] Esperimento {exp_id}")

    # carica grafi
    G_logical = load_graph_json(logical_path)
    G_physical = load_graph_json(physical_path)

    start = time.perf_counter()

    # embedding minorminer
    embedding = minorminer.find_embedding(
        G_logical.edges(),
        G_physical.edges(),
        timeout=exp.get("timeout_seconds", 10),
        tries=100,
        random_seed=123
    )

    elapsed = time.perf_counter() - start

    result = {
        "experiment_id": exp_id,
        "success": bool(embedding),
        "time_seconds": elapsed,
        "num_logical_nodes": G_logical.number_of_nodes(),
        "num_physical_nodes": G_physical.number_of_nodes(),
        "embedding": {},
        "max_chain_length": None,
        "avg_chain_length": None,
        "used_edges": []  # salveremo qui gli archi fisici usati
    }

    if embedding:
        chains = list(embedding.values())
        lengths = [len(c) for c in chains]

        result["embedding"] = {str(k): list(v) for k, v in embedding.items()}
        result["max_chain_length"] = max(lengths)
        result["avg_chain_length"] = sum(lengths) / len(lengths)

        # ---------------------------------------------------------
        # CALCOLO ARCHI FISICI USATI (per plot)
        # ---------------------------------------------------------
        used_edges = set()
        for u_log, v_log in G_logical.edges():
            if u_log in embedding and v_log in embedding:
                # prendi solo il primo nodo della catena (chain1)
                u_phys = normalize_node(list(embedding[u_log])[0])
                v_phys = normalize_node(list(embedding[v_log])[0])
                used_edges.add(tuple(sorted((u_phys, v_phys))))
        result["used_edges"] = list(used_edges)

    # crea cartella output
    out_dir = os.path.join(output_base, str(exp_id))
    os.makedirs(out_dir, exist_ok=True)

    # salva embedding minorminer
    out_path = os.path.join(out_dir, "minorminer_result.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"[ MM ] Successo: {result['success']} | "
          f"Tempo: {elapsed:.4f}s | "
          f"Max chain: {result['max_chain_length']} | "
          f"Archi fisici usati: {len(used_edges)}")

    return result

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    yaml_path = "config.yaml"  # percorso del tuo YAML

    with open(yaml_path, "r") as f:
        config = yaml.safe_load(f)

    experiments = config["experiments"]
    output_base = config.get("output_dir", "outputs")

    print("\n=== AVVIO ESPERIMENTI MINORMINER ===")

    summary = []

    for exp in experiments:
        res = run_minorminer_experiment(exp, output_base)
        summary.append(res)

    # Salva riepilogo globale
    summary_path = os.path.join(output_base, "minorminer_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== COMPLETATO ===")
    print(f"Riepilogo salvato in {summary_path}")


if __name__ == "__main__":
    main()
