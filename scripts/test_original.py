import json
import networkx as nx
import minorminer
import sys
import matplotlib.pyplot as plt

# Se disponibile, usa D-Wave layouts
try:
    import dwave_networkx as dnx
    DWAVE_AVAILABLE = True
except ImportError:
    DWAVE_AVAILABLE = False

# -----------------------------
# CARICAMENTO GRAFI
# -----------------------------
def load_graph_json(path):
    """Carica un grafo da file JSON in networkx"""
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
    return G

# -----------------------------
# EMBEDDING MINORMINER CON VERIFICA
# -----------------------------
def embed_with_fixed_nodes(G_logical, G_physical, fixed_chains=None, timeout=30):
    fixed_chains = fixed_chains or {}
    print("[INFO] Nodi fissati prima dell'embedding:")
    for n, qset in fixed_chains.items():
        print(f"  Nodo logico {n} -> qubit fisico {sorted(list(qset))}")

    embedding, valid = minorminer.find_embedding(
        G_logical.edges(),
        G_physical.edges(),
        fixed_chains=fixed_chains,
        timeout=timeout,
        return_overlap=True
    )

    if embedding:
        print("[INFO] Embedding trovato, validità controllata:", valid)
        for n in sorted(embedding.keys()):
            print(f"{n} -> {embedding[n]}")
    else:
        print("[FAIL] Nessun embedding trovato.")
    return embedding, valid

# -----------------------------
# CHECK ONE-TO-ONE
# -----------------------------
def is_one_to_one(embedding):
    if embedding is None:
        return False
    all_single = all(len(v) == 1 for v in embedding.values())
    all_unique = len([q for v in embedding.values() for q in v]) == len(set([q for v in embedding.values() for q in v]))
    return all_single and all_unique

# -----------------------------
# VISUALIZZAZIONE EMBEDDING CON CONTROLLO ARCHI REALI
# -----------------------------
def plot_embedding_dwave(G_phys, G_logical, embedding):
    # Posizioni nodi fisici
    if DWAVE_AVAILABLE:
        try:
            pos = dnx.chimera_layout(G_phys)  # sostituire con pegasus_layout se necessario
        except:
            pos = nx.spring_layout(G_phys, seed=42)
    else:
        pos = nx.spring_layout(G_phys, seed=42)

    # Colori dei nodi fisici
    node_colors = []
    phys_to_logical = {}
    for log_node, phys_nodes in embedding.items():
        for q in phys_nodes:
            phys_to_logical[q] = log_node

    for n in G_phys.nodes():
        if n in phys_to_logical:
            node_colors.append('tab:blue')
        else:
            node_colors.append('lightgray')

    plt.figure(figsize=(12, 10))
    nx.draw(G_phys, pos, node_color=node_colors, with_labels=True,
            node_size=400, edge_color="gray", font_weight="bold")

    # Disegna archi logici mappati solo se esistono nell'hardware
    logical_edges = []
    for u, v in G_logical.edges():
        if u in embedding and v in embedding:
            for u_phys in embedding[u]:
                for v_phys in embedding[v]:
                    if G_phys.has_edge(u_phys, v_phys):  # <- controllo reale
                        logical_edges.append((u_phys, v_phys))

    # Stampa archi fisici reali
    print("[INFO] Archi fisici effettivamente coinvolti nell'embedding logico:")
    for e in logical_edges:
        print(f"  {e[0]} -- {e[1]}")

    nx.draw_networkx_edges(G_phys, pos, edgelist=logical_edges,
                           edge_color='red', width=2, alpha=0.7)

    # Etichette dei nodi logici
    labels = {q: str(log_node) for log_node, nodes in embedding.items() for q in nodes}
    nx.draw_networkx_labels(G_phys, pos, labels=labels, font_color="black")

    plt.title("Embedding logico -> fisico con archi fisici reali (rosso)")
    plt.show()



# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso:\n  python simple_embed.py logical.json physical.json")
        sys.exit(1)

    logical_path = sys.argv[1]
    physical_path = sys.argv[2]

    # Carica grafi
    G_log = load_graph_json(logical_path)
    G_phys = load_graph_json(physical_path)

    # Esempio nodi fissati
    fixed_chains = {
        0: {35}, 1: {39}, 2: {8}, 3: {15}, 4: {14}, 5: {9}, 6: {34}, 7: {12}
    }

    # Calcola embedding
    embedding, valid = embed_with_fixed_nodes(G_log, G_phys, fixed_chains)

    if embedding:
        if is_one_to_one(embedding):
            print("[INFO] Embedding trovato ed è ONE-TO-ONE")
        else:
            print("[WARN] Embedding trovato ma NON è one-to-one")
        # Disegna embedding con archi logici
        plot_embedding_dwave(G_phys, G_log, embedding)
    else:
        print("[FAIL] Nessun embedding trovato")
