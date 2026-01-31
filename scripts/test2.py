import json
import networkx as nx
import minorminer
import sys
import re

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
# VERIFICA ARCHI LOGICI
# ---------------------------------------------------------
def respects_logical_edges(G_log, embedding, G_phys):
    for u, v in G_log.edges():
        if not any(G_phys.has_edge(a, b) for a in embedding[u] for b in embedding[v]):
            print(f"[FAIL] Arco logico ({u},{v}) NON rispettato")
            return False
    return True

# ---------------------------------------------------------
# WRAPPER DI TRACE PER MINORMINER
# ---------------------------------------------------------
def traced_find_embedding(step_id, G_log, G_phys, fixed_chains, timeout):
    print("\n" + "=" * 70)
    print(f"[MINORMINER CALL #{step_id}]")
    if fixed_chains:
        print("Fixed chains:")
        for n in sorted(fixed_chains):
            print(f"  {n} -> {sorted(fixed_chains[n])}")
    else:
        print("Fixed chains: NONE")

    used = sorted(q for ch in fixed_chains.values() for q in ch)
    print("Used qubits:", used)
    print("=" * 70)

    emb = minorminer.find_embedding(
        G_log.edges(),
        G_phys.edges(),
        fixed_chains=fixed_chains,
        timeout=timeout
    )

    if not emb:
        print("[RESULT] FAIL (no embedding)")
        return None

    print("[RESULT] EMBEDDING FOUND:")
    for n in sorted(emb):
        print(f"  {n} -> {sorted(emb[n])}")

    return emb

# ---------------------------------------------------------
# EMBEDDING ITERATIVO SENZA CHECK ALLOWED
# ---------------------------------------------------------
def progressive_embedding(G_logical, G_physical, allowed_dict, forced_dict, timeout=30, max_retries=1):
    step_id = 0

    # -------------------------------
    # FASE 0: fissaggi hard (forced o allowed unico)
    # -------------------------------
    fixed_hard = {}
    for n in allowed_dict:
        if len(forced_dict.get(n, [])) == 1:
            fixed_hard[n] = set(forced_dict[n])
            print(f"[FIXED-HARD] Nodo {n} forced a {forced_dict[n][0]}")
        elif len(allowed_dict[n]) == 1:
            fixed_hard[n] = set(allowed_dict[n])
            print(f"[FIXED-HARD] Nodo {n} allowed unico a {allowed_dict[n][0]}")

    free_nodes = [n for n in allowed_dict if n not in fixed_hard]

    # -------------------------------
    # FASE ITERATIVA: rilancio Minorminer finché archi logici rispettati
    # -------------------------------
    for attempt in range(1, max_retries + 1):
        print(f"\n[ATTEMPT {attempt}/{max_retries}]")
        fixed = dict(fixed_hard)

        emb = traced_find_embedding(step_id, G_logical, G_physical, fixed, timeout)
        step_id += 1

        if not emb:
            print("[Minorminer FAIL] Riprovo...")
            continue

        if respects_logical_edges(G_logical, emb, G_physical):
            print("[SUCCESS] Embedding valido trovato!")
            return emb
        else:
            print("[FAIL] Embedding trovato non rispetta archi logici, rilancio Minorminer...")

    print("[FAIL] Impossibile trovare embedding valido dopo massimo tentativi")
    return None

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python test.py logical.json physical.json unsat_analysis.txt")
        sys.exit(1)

    G_log = load_graph_json(sys.argv[1])
    G_phys = load_graph_json(sys.argv[2])
    allowed, forced = parse_unsat_analysis(sys.argv[3])

    num_attempts = 100
    best_emb = None
    best_max_chain = float("inf")
    best_num_nodes_max_chain = float("inf")

    for attempt in range(1, num_attempts + 1):
        print("\n" + "#" * 70)
        print(f"[ATTEMPT {attempt}/{num_attempts}]")
        emb = progressive_embedding(G_log, G_phys, allowed, forced)

        if emb is None:
            print("[ATTEMPT FALLITO]")
            continue

        chain_lengths = [len(chain) for chain in emb.values()]
        max_chain_len = max(chain_lengths)
        num_nodes_max_chain = chain_lengths.count(max_chain_len)

        print(f"[ATTEMPT {attempt}] Massima chain: {max_chain_len}, Nodi con catena massima: {num_nodes_max_chain}")

        if (max_chain_len < best_max_chain) or \
           (max_chain_len == best_max_chain and num_nodes_max_chain < best_num_nodes_max_chain):
            best_max_chain = max_chain_len
            best_num_nodes_max_chain = num_nodes_max_chain
            best_emb = emb
            print(f"[ATTEMPT {attempt}] Nuovo embedding migliore trovato!")

        if best_max_chain == 1 and best_num_nodes_max_chain == 0:
            print("[EMBEDDING OTTIMALE TROVATO]")
            break

    if best_emb:
        print("\n[EMBEDDING FINALE SELEZIONATO]")
        print(f"Massima chain: {best_max_chain}, Nodi con catena massima: {best_num_nodes_max_chain}")
        for n in sorted(best_emb):
            print(f"{n} -> {sorted(best_emb[n])}")
        sys.exit(0)
    else:
        print("[NESSUN EMBEDDING TROVATO]")
        sys.exit(2)
