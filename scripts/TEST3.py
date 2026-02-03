import json
import networkx as nx
import minorminer
import sys
import re
import time
import copy
import os

# ---------------------------------------------------------
# CARICAMENTO GRAFI
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
# PARSING UNSAT_ANALYSIS.TXT
# ---------------------------------------------------------
def parse_unsat_analysis(path):
    allowed_dict = {}
    forced_dict = {}

    with open(path) as f:
        lines = f.readlines()

    current_node = None
    for line in lines:
        line = line.strip()
        if line.startswith("Nodo logico"):
            current_node = int(line.split()[2].strip(":"))
        elif line.startswith("Allowed"):
            vals = line.split(":", 1)[1].strip().strip("[] ")
            allowed_dict[current_node] = [
                int(x) for x in re.split(r",\s*", vals) if x.isdigit()
            ]
        elif line.startswith("Forced"):
            vals = line.split(":", 1)[1].strip().strip("[] ")
            forced_dict[current_node] = [
                int(x) for x in re.split(r",\s*", vals) if x.isdigit()
            ]

    return allowed_dict, forced_dict


# ---------------------------------------------------------
# CONTROLLI DI VALIDITÀ
# ---------------------------------------------------------
def respects_logical_edges(G_log, embedding, G_phys):
    for u, v in G_log.edges():
        if not any(
            G_phys.has_edge(a, b)
            for a in embedding.get(u, [])
            for b in embedding.get(v, [])
        ):
            return False
    return True


# ---------------------------------------------------------
# METRICHE EMBEDDING
# ---------------------------------------------------------
def embedding_metrics(embedding):
    used_physical = set()
    lengths = []

    for chain in embedding.values():
        used_physical.update(chain)
        lengths.append(len(chain))

    return {
        "num_physical_used": len(used_physical),
        "max_chain_length": max(lengths),
        "avg_chain_length": sum(lengths) / len(lengths),
    }


# ---------------------------------------------------------
# MINORMINER CON TIMER
# ---------------------------------------------------------
def traced_find_embedding(G_log, G_phys, fixed_chains, timeout):
    start = time.perf_counter()
    emb = minorminer.find_embedding(
        G_log.edges(),
        G_phys.edges(),
        fixed_chains=fixed_chains,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - start
    return emb, elapsed


# ---------------------------------------------------------
# EMBEDDING ITERATIVO (FIRST HIT)
# ---------------------------------------------------------
def progressive_embedding(
    G_logical,
    G_physical,
    allowed_dict,
    forced_dict,
    timeout=30,
    max_attempts=100,
):
    # --- FIXED HARD ---
    fixed_hard = {}
    for n in allowed_dict:
        if len(forced_dict.get(n, [])) == 1:
            fixed_hard[n] = set(forced_dict[n])
        elif len(allowed_dict[n]) == 1:
            fixed_hard[n] = set(allowed_dict[n])

    # --- TENTATIVI ---
    for attempt in range(1, max_attempts + 1):
        fixed = copy.deepcopy(fixed_hard)
        emb, elapsed = traced_find_embedding(
            G_logical, G_physical, fixed, timeout
        )

        if not emb:
            print(f"[Attempt {attempt}] Nessun embedding trovato")
            continue

        if not respects_logical_edges(G_logical, emb, G_physical):
            print(f"[Attempt {attempt}] Embedding non rispetta archi logici")
            continue

        metrics = embedding_metrics(emb)

        result = {
            "success": True,
            "attempt": attempt,
            "time_seconds": elapsed,
            "embedding": emb,
            **metrics,
        }

        print(
            f"[Attempt {attempt}] EMBEDDING ACCETTATO | "
            f"Nodi fisici: {metrics['num_physical_used']} | "
            f"Max chain: {metrics['max_chain_length']} | "
            f"Avg chain: {metrics['avg_chain_length']:.2f}"
        )

        # PRIMO EMBEDDING VALIDO → STOP
        return result

    #  Nessun embedding trovato
    return None


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python script.py logical.json physical.json unsat_analysis.txt")
        sys.exit(1)

    G_log = load_graph_json(sys.argv[1])
    G_phys = load_graph_json(sys.argv[2])
    allowed, forced = parse_unsat_analysis(sys.argv[3])

    result = progressive_embedding(
        G_log,
        G_phys,
        allowed,
        forced,
        timeout=30,
        max_attempts=100,
    )

    if not result:
        print("[FAIL] Nessun embedding valido trovato in 100 tentativi")
        sys.exit(2)

    # -----------------------------------------------------
    # OUTPUT STDOUT
    # -----------------------------------------------------
    print("\n[SUCCESS] Primo embedding valido trovato")
    print(f"Tentativo: {result['attempt']}")
    print(f"Tempo: {result['time_seconds']:.8f}s")
    print(f"Nodi fisici usati: {result['num_physical_used']}")
    print(f"Max chain: {result['max_chain_length']}")
    print(f"Avg chain: {result['avg_chain_length']:.2f}")

    for n in sorted(result["embedding"]):
        print(f"{n} -> {sorted(result['embedding'][n])}")

    # -----------------------------------------------------
    # SALVATAGGIO JSON
    # -----------------------------------------------------
    unsat_dir = os.path.dirname(os.path.abspath(sys.argv[3]))
    os.makedirs(unsat_dir, exist_ok=True)

    output_file = os.path.join(
        unsat_dir, "sat_minorminer_result_FIRSTHIT.json"
    )

    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n[INFO] Risultato salvato in {output_file}")
    sys.exit(0)
