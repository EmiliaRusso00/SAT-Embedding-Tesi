import networkx as nx
import os
import json
import random

try:
    import dwave_networkx as dnx
    DWAVE_AVAILABLE = True
except ImportError:
    DWAVE_AVAILABLE = False

# ---------------------------------------------------------
# SALVATORE FILE TXT
# ---------------------------------------------------------
def save_graph_txt(G, path):
    with open(path, 'w') as f:
        for u, v in G.edges():
            f.write(f"{u} {v}\n")
        for u in nx.isolates(G):
            f.write(f"{u}\n")
    print(f"[ OK ] Grafo salvato in {path}")

# ---------------------------------------------------------
# SALVATORE FILE JSON
# ---------------------------------------------------------
def save_graph_json(G, path, metadata):
    nodes_list = [[n, G.nodes[n]] for n in G.nodes()]
    edges_list = [list(e) for e in G.edges()]
    data = {
        "nodes": nodes_list,
        "edges": edges_list,
        "metadata": metadata,
        "graph_attributes": dict(G.graph)
    }
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"[ OK ] Grafo JSON salvato in {path}")

# ---------------------------------------------------------
# GENERATORE ZEPHYR
# ---------------------------------------------------------
def gen_zephyr(m, t):
    if not DWAVE_AVAILABLE:
        raise RuntimeError("dwave_networkx NON è installato. Installa con: pip install dwave-networkx")
    return dnx.zephyr_graph(m, t)

# ---------------------------------------------------------
# GENERAZIONE SOTTOGRAFO
# ---------------------------------------------------------
def generate_subgraph_random(G, mode, num):
    """
    Genera un sottografo casuale del grafo G.
    mode: 'nodes' per sottografo indotto da num nodi casuali
          'edges' per sottografo con num archi casuali
    """
    if mode == 'nodes':
        if num > len(G.nodes()):
            raise ValueError(f"Numero di nodi richiesto ({num}) maggiore del totale ({len(G.nodes())})")
        selected_nodes = random.sample(list(G.nodes()), num)
        subgraph = G.subgraph(selected_nodes).copy()
        return subgraph
    elif mode == 'edges':
        if num > len(G.edges()):
            raise ValueError(f"Numero di archi richiesto ({num}) maggiore del totale ({len(G.edges())})")
        selected_edges = random.sample(list(G.edges()), num)
        subgraph = nx.Graph()
        subgraph.add_edges_from(selected_edges)
        # Copia attributi dei nodi se presenti
        for node in subgraph.nodes():
            if node in G.nodes():
                subgraph.nodes[node].update(G.nodes[node])
        return subgraph
    else:
        raise ValueError("Modalità non valida: scegliere 'nodes' o 'edges'")

def generate_subgraph_custom(G, nodes_to_remove):
    """
    Rimuove dal grafo G i nodi indicati dall'utente.
    """
    subgraph = G.copy()
    missing_nodes = [n for n in nodes_to_remove if n not in subgraph]
    if missing_nodes:
        raise ValueError(f"Nodi non presenti nel grafo: {missing_nodes}")
    subgraph.remove_nodes_from(nodes_to_remove)
    return subgraph

# ---------------------------------------------------------
# MENU E GENERAZIONE
# ---------------------------------------------------------
def main():
    print("\n=== GENERATORE DI SOTTOGRAFI ZEPHYR ===")

    # Parametri Zephyr
    m = int(input("Dimensione m per Zephyr (es. 1..20): "))
    t = int(input("Dimensione bipartizione t per Zephyr (tipicamente 4): "))

    # Genera Zephyr
    try:
        G = gen_zephyr(m, t)
        print(f"Zephyr {m}x{t} generato con {len(G.nodes())} nodi e {len(G.edges())} archi.")
    except RuntimeError as e:
        print(e)
        return

    # Scelta modalità sottografo
    print("\nModalità sottografo:")
    print("1) Rimuovere nodi specifici")
    print("2) Sottografo casuale (per numero di nodi o archi)")
    choice = input("Scelta: ")

    if choice == "1":
        nodes_input = input("Inserisci nodi da rimuovere separati da spazio: ")
        try:
            nodes_to_remove = [int(n.strip()) for n in nodes_input.split()]
            subgraph = generate_subgraph_custom(G, nodes_to_remove)
        except ValueError as e:
            print(e)
            return
    elif choice == "2":
        print("Selezione casuale:")
        print("1) Per numero di nodi")
        print("2) Per numero di archi")
        sub_choice = input("Scelta: ")
        if sub_choice == "1":
            mode = 'nodes'
            num = int(input(f"Numero di nodi da selezionare (max {len(G.nodes())}): "))
        elif sub_choice == "2":
            mode = 'edges'
            num = int(input(f"Numero di archi da selezionare (max {len(G.edges())}): "))
        else:
            print("Scelta non valida.")
            return
        try:
            subgraph = generate_subgraph_random(G, mode, num)
        except ValueError as e:
            print(e)
            return
    else:
        print("Scelta non valida.")
        return

    print(f"Sottografo generato: {len(subgraph.nodes())} nodi, {len(subgraph.edges())} archi.")

    # Metadata
    metadata = {"type": "zephyr", "m": m, "t": t, "original_dwave_graph": True}

    # Salvataggio
    os.makedirs("graphs", exist_ok=True)
    filename = input("\nNome file output (senza estensione): ")
    save_graph_txt(subgraph, f"graphs/{filename}.txt")
    save_graph_json(subgraph, f"graphs/{filename}.json", metadata)

    print("\nFatto!")

if __name__ == "__main__":
    main()
