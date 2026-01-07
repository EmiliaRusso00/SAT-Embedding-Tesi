import os
import json
import matplotlib.pyplot as plt
import networkx as nx
from utils import ensure_dir

try:
    import dwave_networkx as dnx
    from dwave_networkx import draw_chimera, draw_pegasus, draw_zephyr
    DWAVE_AVAILABLE = True
except ImportError:
    DWAVE_AVAILABLE = False


def normalize_node(n):
    if isinstance(n, tuple):
        return n
    if isinstance(n, list):
        return tuple(n)
    return (n,)

# ================================================================
# POSIZIONI AUTOMATICHE 2D/3D
# ================================================================
def compute_positions(G, metadata=None, dwave_generated=False):
    nodes = list(G.nodes())

    if DWAVE_AVAILABLE and metadata and dwave_generated:
        gtype = metadata.get("type", "").lower()
        try:
            if gtype == "chimera":
                G_dwave = dnx.chimera_graph(metadata.get("rows"), metadata.get("cols"), metadata.get("tile", 4))
                return dnx.chimera_layout(G_dwave), 2
            elif gtype == "pegasus":
                G_dwave = dnx.pegasus_graph(metadata.get("m"))
                return dnx.pegasus_layout(G_dwave), 2
            elif gtype == "zephyr":
                G_dwave = dnx.zephyr_graph(metadata.get("m"), metadata.get("t"))
                return dnx.zephyr_layout(G_dwave), 2
        except Exception as e:
            print(f"[WARN] Non posso generare layout {gtype} originale: {e}. Uso spring_layout fallback.")

    if all(isinstance(n, tuple) and len(n) == 2 for n in nodes):
        return {n: (n[0], n[1]) for n in nodes}, 2
    if all(isinstance(n, tuple) and len(n) == 3 for n in nodes):
        return {n: (n[0], n[1], n[2]) for n in nodes}, 3

    return nx.spring_layout(G, seed=42), 2


# ================================================================
# PLOT GRAFICO GENERICO 2D/3D
# ================================================================
def plot_graph(G, pos=None, dim=2, title="Graph", node_colors=None,
               node_labels=None, edge_colors=None, edge_widths=None,
               figsize=(6, 6), save_path=None, dwave_draw=False, dwave_type=None,
               show_labels=False):

    ensure_dir(os.path.dirname(save_path) if save_path else ".")

    fig = plt.figure(figsize=figsize)  # creo sempre la figura
    try:
        # ------------------------
        # D-WAVE DRAW
        # ------------------------
        if dwave_draw and DWAVE_AVAILABLE and dwave_type:
            try:
                if dwave_type == "chimera":
                    draw_chimera(G, node_size=10, node_color=node_colors or 'lightblue', edge_color=edge_colors or 'black')
                elif dwave_type == "pegasus":
                    draw_pegasus(G, node_size=10, node_color=node_colors or 'lightcoral', edge_color=edge_colors or 'black')
                elif dwave_type == "zephyr":
                    draw_zephyr(G, node_size=10, node_color=node_colors or 'mediumpurple', edge_color=edge_colors or 'black')

                plt.title(title)

                # etichette opzionali
                if show_labels:
                    if node_labels is None:
                        node_labels = {n: str(n) for n in G.nodes()}
                    pos_for_labels = pos if pos is not None else nx.spring_layout(G, seed=42)
                    nx.draw_networkx_labels(G, pos_for_labels, labels=node_labels, font_color='black', font_weight='bold', font_size=6)

                if save_path:
                    plt.savefig(save_path, bbox_inches="tight", dpi=400)
                return  # esco, plt.close(fig) verrà eseguito nel finally

            except ValueError:
                print(f"[WARN] draw_{dwave_type} richiede grafo originale. Uso NetworkX draw fallback.")

        # ------------------------
        # FALLBACK NETWORKX
        # ------------------------
        if node_labels is None:
            node_labels = {n: str(n) for n in G.nodes()}
        if edge_colors is None:
            edge_colors = ['gray'] * len(G.edges())
        if edge_widths is None:
            edge_widths = [1] * len(G.edges())

        if dim == 3:
            from mpl_toolkits.mplot3d import Axes3D  # noqa
            ax = fig.add_subplot(111, projection='3d')
            xs = [pos[n][0] for n in G.nodes()]
            ys = [pos[n][1] for n in G.nodes()]
            zs = [pos[n][2] for n in G.nodes()]
            ax.scatter(xs, ys, zs, c=node_colors, s=80)
            for (u, v), ec, ew in zip(G.edges(), edge_colors, edge_widths):
                x = [pos[u][0], pos[v][0]]
                y = [pos[u][1], pos[v][1]]
                z = [pos[u][2], pos[v][2]]
                ax.plot(x, y, z, color=ec, linewidth=ew)
            if show_labels:
                for n in G.nodes():
                    x, y, z = pos[n]
                    ax.text(x, y, z, node_labels[n], color='black', fontsize=5)
            ax.set_title(title)
        else:
            ax = fig.add_subplot(111)
            nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=edge_widths, alpha=0.8, ax=ax)
            nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=10, ax=ax)
            if show_labels:
                nx.draw_networkx_labels(G, pos, labels=node_labels, font_color='black', font_weight='bold', ax=ax, font_size=6)
            plt.title(title)

        if save_path:
            plt.savefig(save_path, bbox_inches="tight", dpi=400)

    finally:
        # chiudo sempre la figura per liberare memoria
        plt.close(fig)



# ================================================================
# PLOT EMBEDDING CON NODI RIDOTTI
# ================================================================
def plot_embedding(G_logical, G_physical, solution_map, save_dir, exp_id,
                   reduced_file=None, logical_metadata=None, physical_metadata=None,
                   logical_dwave=False, physical_dwave=False, show_labels=False):

    ensure_dir(save_dir)

# ============================================================
# CARICAMENTO RIDOTTO — VERSIONE CORRETTA (unica)
# ============================================================
    reduced_nodes = set()
    reduced_edges = set()

    if reduced_file and os.path.isfile(reduced_file):
        with open(reduced_file, "r") as f:
            data = json.load(f)

        for n in data.get("nodes", []):
            if isinstance(n, int):
                reduced_nodes.add((n,))
            else:
                reduced_nodes.add(tuple(int(x) for x in n))

        for e in data.get("edges", []):
            u_raw, v_raw = e
            u = (u_raw,) if isinstance(u_raw, int) else tuple(int(x) for x in u_raw)
            v = (v_raw,) if isinstance(v_raw, int) else tuple(int(x) for x in v_raw)
            reduced_edges.add(tuple(sorted((u, v))))


# ------------------------------------------------------------
# MINORMINER RESULT
# ------------------------------------------------------------

    mm_nodes, mm_edges = set(), set()
    mm_path = os.path.join("outputs", str(exp_id), "minorminer_result.json")

    if os.path.isfile(mm_path):
        with open(mm_path) as f:
            mm = json.load(f)

        # --- NODI fisici occupati ---
        for chain in mm.get("embedding", {}).values():
            chain_nodes = [normalize_node(x) for x in chain]
            for n in chain_nodes:
                mm_nodes.add(n)
        # --- Archi fisici usati (dal campo saved used_edges) ---
        for e in mm.get("used_edges", []):
            u, v = e
            mm_edges.add((normalize_node(u), normalize_node(v)))
# ============================================================
# LOGICAL PLOT
# ============================================================
    pos_log, dim_log = compute_positions(G_logical, logical_metadata, dwave_generated=logical_dwave)

    plot_graph(G_logical, pos_log, dim_log,
               title="Logical Graph",
               node_colors=['skyblue'] * len(G_logical.nodes()),
               save_path=os.path.join(save_dir, f"exp_{exp_id}_logical.png"),
               dwave_draw=logical_dwave,
               dwave_type=logical_metadata.get("type") if logical_metadata else None,
               show_labels=show_labels)

# ============================================================
# PHYSICAL GRAPH — STRUTTURA + RIDOTTO + MINORMINER
# ============================================================
    pos_phys, dim_phys = compute_positions(
        G_physical,
        physical_metadata,
        dwave_generated=physical_dwave
    )

    # ------------------------
    # NODI
    # ------------------------
    node_colors = []

    for n in G_physical.nodes():
        nt = normalize_node(n)

        if nt in mm_nodes:
            node_colors.append("red")          # Minorminer
        elif nt in reduced_nodes:
            node_colors.append("plum")         # SAT ridotto
        else:
            node_colors.append("lightgray")    # inutilizzato

    # ------------------------
    # ARCHI
    # ------------------------
    edge_colors = []
    edge_widths = []

    for u, v in G_physical.edges():
        e = tuple(sorted((normalize_node(u), normalize_node(v))))

        if e in mm_edges:
            edge_colors.append("red")          # catena Minorminer
            edge_widths.append(1.2)
        elif e in reduced_edges:
            edge_colors.append("purple")       # SAT ridotto
            edge_widths.append(0.6)
        else:
            edge_colors.append("gray")
            edge_widths.append(0.4)

    plot_graph(
        G_physical,
        pos_phys,
        dim_phys,
        title="Physical Graph (Minorminer + Reduced SAT)",
        node_colors=node_colors,
        edge_colors=edge_colors,
        edge_widths=edge_widths,
        save_path=os.path.join(save_dir, f"exp_{exp_id}_physical.png"),
        dwave_draw=physical_dwave,
        dwave_type=physical_metadata.get("type") if physical_metadata else None,
        show_labels=show_labels
    )

    # ============================================================
    # EMBEDDING — LOGICAL → PHYSICAL
    # ============================================================
    labels = {}
    used_edges = set()

    # ------------------------
    # ARCHI LOGICI USATI (SAT)
    # ------------------------
    if solution_map:
        for u_log, v_log in G_logical.edges():
            if u_log in solution_map and v_log in solution_map:
                up = normalize_node(solution_map[u_log])
                vp = normalize_node(solution_map[v_log])
                used_edges.add(tuple(sorted((up, vp))))

    # ------------------------
    # NODI (EMBEDDING)
    # ------------------------
    node_colors = []
    edge_colors = []
    edge_widths = []

    for n in G_physical.nodes():
        nt = normalize_node(n)

        mapped_logical = [
            l for l, p in solution_map.items()
            if normalize_node(p) == nt
        ] if solution_map else []

        if nt in mm_nodes:
            node_colors.append("red")           # Minorminer
        elif mapped_logical:
            node_colors.append("lightblue")     # SAT embedding
        elif nt in reduced_nodes:
            node_colors.append("plum")          # SAT ridotto
        else:
            node_colors.append("lightgray")

        labels[n] = ",".join(map(str, mapped_logical)) if mapped_logical else str(n)

    # ------------------------
    # ARCHI (EMBEDDING)
    # ------------------------
    for u, v in G_physical.edges():
        e = tuple(sorted((normalize_node(u), normalize_node(v))))

        if e in mm_edges:
            edge_colors.append("red")
            edge_widths.append(1.2)
        elif e in used_edges:
            edge_colors.append("aqua")          # SAT embedding
            edge_widths.append(0.6)
        elif e in reduced_edges:
            edge_colors.append("purple")
            edge_widths.append(0.5)
        else:
            edge_colors.append("lightgray")
            edge_widths.append(0.4)

    plot_graph(
        G_physical,
        pos_phys,
        dim_phys,
        title="Embedding: Logical → Physical (SAT vs Minorminer)",
        node_colors=node_colors,
        edge_colors=edge_colors,
        edge_widths=edge_widths,
        node_labels=labels,
        save_path=os.path.join(save_dir, f"exp_{exp_id}_embedding.png"),
        dwave_draw=physical_dwave,
        dwave_type=physical_metadata.get("type") if physical_metadata else None,
        show_labels=show_labels
    )

# ================================================================
# NO EMBEDDING
# ================================================================
def plot_noembedding(G_logical, G_physical, save_dir, exp_id,
                     reduced_file=None,
                     logical_metadata=None, physical_metadata=None,
                     logical_dwave=False, physical_dwave=False, show_labels=False):

    ensure_dir(save_dir)

    # ============================================================
    # GRAFO RIDOTTO 
    # ============================================================
    reduced_nodes = set()
    reduced_edges = set()

    if reduced_file and os.path.isfile(reduced_file):
        with open(reduced_file, "r") as f:
            data = json.load(f)

        for n in data.get("nodes", []):
            if isinstance(n, int):
                reduced_nodes.add((n,))
            else:
                reduced_nodes.add(tuple(int(x) for x in n))

        for u_raw, v_raw in data.get("edges", []):
            u = (u_raw,) if isinstance(u_raw, int) else tuple(int(x) for x in u_raw)
            v = (v_raw,) if isinstance(v_raw, int) else tuple(int(x) for x in v_raw)
            reduced_edges.add(tuple(sorted((u, v))))

    # ============================================================
    # LOGICAL GRAPH
    # ============================================================
    pos_log, dim_log = compute_positions(G_logical, logical_metadata, dwave_generated=logical_dwave)
    plot_graph(
        G_logical, pos_log, dim_log,
        title="Logical Graph",
        node_colors=['skyblue'] * len(G_logical.nodes()),
        save_path=os.path.join(save_dir, f"exp_{exp_id}_logical.png"),
        dwave_draw=logical_dwave,
        dwave_type=logical_metadata.get("type") if logical_metadata else None,
        show_labels=show_labels
    )

    # ============================================================
    # PHYSICAL GRAPH — COLORI BASATI SU RIDOTTO
    # ============================================================
    pos_phys, dim_phys = compute_positions(G_physical, physical_metadata, dwave_generated=physical_dwave)

    node_colors = []
    for n in G_physical.nodes():
        n_tuple = (n,) if isinstance(n, int) else tuple(n)
        node_colors.append("plum" if n_tuple in reduced_nodes else "lightgray")

    edge_colors = []
    edge_widths = []
    for u, v in G_physical.edges():
        u_t = (u,) if isinstance(u, int) else tuple(u)
        v_t = (v,) if isinstance(v, int) else tuple(v)
        edge = tuple(sorted((u_t, v_t)))

        if edge in reduced_edges:
            edge_colors.append("purple")
            edge_widths.append(0.7)
        else:
            edge_colors.append("gray")
            edge_widths.append(0.5)

    plot_graph(
        G_physical, pos_phys, dim_phys,
        title="Physical Graph (Reduced Highlighted)",
        node_colors=node_colors,
        edge_colors=edge_colors,
        edge_widths=edge_widths,
        save_path=os.path.join(save_dir, f"exp_{exp_id}_physical.png"),
        dwave_draw=physical_dwave,
        dwave_type=physical_metadata.get("type") if physical_metadata else None,
        show_labels=show_labels
    )

    print(f"[INFO] Saved logical and physical plots (with reduced colors) to {save_dir}")
