import networkx as nx
import minorminer
import dwave_networkx as dnx

DWAVE_AVAILABLE = True

# ---------------------------------------------------------
# GENERATORI STANDARD
# ---------------------------------------------------------
def gen_random_graph(n, p=0.3):
    return nx.erdos_renyi_graph(n, p)

def gen_tree(n):
    return nx.random_labeled_tree(n)

def gen_grid_2d(m, n):
    return nx.grid_2d_graph(m, n)

def gen_grid_3d(m, n, p):
    return nx.grid_graph(dim=[m, n, p])

def gen_clique(n):
    return nx.complete_graph(n)

def gen_bipartite(a, b):
    return nx.complete_bipartite_graph(a, b)

def gen_star(n):
    return nx.star_graph(n)

def gen_cycle(n):
    return nx.cycle_graph(n)

def gen_line(n):
    return nx.path_graph(n)

def gen_small_world(n, k, p):
    return nx.watts_strogatz_graph(n, k, p)

def gen_scale_free(n):
    return nx.barabasi_albert_graph(n, m=2)


# ---------------------------------------------------------
# GENERATORI D-WAVE
# ---------------------------------------------------------
def gen_chimera(M, N, L):
    return dnx.chimera_graph(M, N, L)

def gen_pegasus(m):
    return dnx.pegasus_graph(m)

def gen_zephyr(m, t):
    return dnx.zephyr_graph(m, t)


# ---------------------------------------------------------
# MENU PER SCELTA GRAFO LOGICO
# ---------------------------------------------------------
def choose_logical_graph():

    print("\n=== SCEGLI IL GRAFO LOGICO ===")
    types = {
        "1": "random",
        "2": "tree",
        "3": "grid2d",
        "4": "grid3d",
        "5": "clique",
        "6": "bipartite",
        "7": "star",
        "8": "cycle",
        "9": "line",
        "10": "smallworld",
        "11": "scalefree"
    }

    for k, v in types.items():
        print(f"{k}) {v}")

    choice = input("\nScelta: ")
    G = None

    if choice == "1":
        n = int(input("Numero nodi: "))
        p = float(input("Probabilità arco: "))
        G = gen_random_graph(n, p)

    elif choice == "2":
        n = int(input("Numero nodi: "))
        G = gen_tree(n)

    elif choice == "3":
        m = int(input("Righe: "))
        n = int(input("Colonne: "))
        G = gen_grid_2d(m, n)

    elif choice == "4":
        x = int(input("X: "))
        y = int(input("Y: "))
        z = int(input("Z: "))
        G = gen_grid_3d(x, y, z)

    elif choice == "5":
        n = int(input("Numero nodi: "))
        G = gen_clique(n)

    elif choice == "6":
        a = int(input("Lato A: "))
        b = int(input("Lato B: "))
        G = gen_bipartite(a, b)

    elif choice == "7":
        n = int(input("Numero foglie: "))
        G = gen_star(n)

    elif choice == "8":
        n = int(input("Numero nodi: "))
        G = gen_cycle(n)

    elif choice == "9":
        n = int(input("Numero nodi: "))
        G = gen_line(n)

    elif choice == "10":
        n = int(input("Numero nodi: "))
        k = int(input("Num. vicini: "))
        p = float(input("Probabilità rewiring: "))
        G = gen_small_world(n, k, p)

    elif choice == "11":
        n = int(input("Numero nodi: "))
        G = gen_scale_free(n)

    else:
        print("Scelta non valida")
        return None

    return G


# ---------------------------------------------------------
# MENU PER SCELTA GRAFO FISICO (D-WAVE)
# ---------------------------------------------------------
def choose_physical_graph():

    print("\n=== SCEGLI IL GRAFO FISICO (D-WAVE) ===")

    types = {
        "1": "chimera",
        "2": "pegasus",
        "3": "zephyr"
    }

    for k, v in types.items():
        print(f"{k}) {v}")

    choice = input("\nScelta: ")
    C = None

    if choice == "1":
        M = int(input("Celle M: "))
        N = int(input("Celle N: "))
        L = int(input("Bipartizione L (tipico 4): "))
        C = gen_chimera(M, N, L)

    elif choice == "2":
        m = int(input("Dimensione m: "))
        C = gen_pegasus(m)

    elif choice == "3":
        m = int(input("Dimensione m: "))
        t = int(input("Bipartizione t: "))
        C = gen_zephyr(m, t)

    else:
        print("Scelta non valida")
        return None

    return C


# ---------------------------------------------------------
# MAIN FLOW
# ---------------------------------------------------------
def main():

    logical = choose_logical_graph()
    if logical is None:
        return

    physical = choose_physical_graph()
    if physical is None:
        return

    print("\n=== AVVIO MINOR MINER ===")
    print("Embedding in corso...")

    embedding = minorminer.find_embedding(
    logical.edges(),
    physical.edges(),
    tries=100,
    timeout=10,
    random_seed=123
)

    if embedding:
        print("\nEmbedding trovato ✔")
        max_chain = max(len(chain) for chain in embedding.values())
        print("Lunghezza massima chain:", max_chain)
    else:
        print("\nEmbedding NON trovato ✘")


if __name__ == "__main__":
    main()
