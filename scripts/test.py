import networkx as nx
import minorminer
import json

def normalize_node(n):
    """Normalizza un nodo come tuple (per consistenza tra tipi diversi)"""
    if isinstance(n, tuple):
        return n
    if isinstance(n, list):
        return tuple(n)
    return (n,)

def compute_physical_edges(G_logical, G_physical, embedding):
    """Restituisce gli archi fisici usati per archi logici e catene"""
    logical_edges = set()
    chain_edges = set()
    
    # Archi fisici che realizzano archi logici
    for u, v in G_logical.edges():
        if u not in embedding or v not in embedding:
            continue
        for pu in embedding[u]:
            for pv in embedding[v]:
                if G_physical.has_edge(pu, pv):
                    logical_edges.add(tuple(sorted((pu, pv))))
    
    # Archi fisici interni alle catene
    for chain in embedding.values():
        chain = list(chain)
        for i in range(len(chain)):
            for j in range(i+1, len(chain)):
                if G_physical.has_edge(chain[i], chain[j]):
                    chain_edges.add(tuple(sorted((chain[i], chain[j]))))
    
    return logical_edges, chain_edges

def embed_graph(G_logical, G_physical, timeout=30):
    """Esegue embedding logico->fisico con Minorminer"""
    print(f"[INFO] Calcolo embedding...")
    
    embedding = minorminer.find_embedding(
        G_logical.edges(),
        G_physical.edges(),
        timeout=timeout
    )
    
    if not embedding:
        print("[WARN] Embedding non trovato!")
        return None
    
    # Calcolo lunghezze catene
    chains = list(embedding.values())
    chain_lengths = [len(c) for c in chains]
    max_chain = max(chain_lengths)
    avg_chain = sum(chain_lengths) / len(chain_lengths)
    
    print(f"[INFO] Embedding trovato!")
    print(f"  Numero nodi logici: {G_logical.number_of_nodes()}")
    print(f"  Numero nodi fisici: {G_physical.number_of_nodes()}")
    print(f"  Massima chain length: {max_chain}")
    print(f"  Lunghezza media chain: {avg_chain:.2f}")
    
    # Archi fisici usati
    logical_edges_phys, chain_edges = compute_physical_edges(G_logical, G_physical, embedding)
    print(f"  Archi fisici per archi logici: {len(logical_edges_phys)}")
    print(f"  Archi fisici interni alle catene: {len(chain_edges)}")
    
    return {
        "embedding": {str(k): list(v) for k, v in embedding.items()},
        "max_chain_length": max_chain,
        "avg_chain_length": avg_chain,
        "physical_edges_logical": list(logical_edges_phys),
        "physical_edges_chain": list(chain_edges)
    }

# -------------------------
# ESEMPIO D'USO
# -------------------------
if __name__ == "__main__":
    import dwave_networkx as dnx

    # Grafo logico: esempio ciclo 8 nodi
    G_log = nx.star_graph(21)

    # Grafo fisico: esempio Chimera C(2)
    G_phys = dnx.zephyr_graph(5,4)

    result = embed_graph(G_log, G_phys)