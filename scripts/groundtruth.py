import os
import json
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# =========================
# CONFIG
# =========================
OUTPUT_DIR = "outputs"
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "minorminer_summary.json")
CSV_OUT = os.path.join(OUTPUT_DIR, "embedding_times_summary.csv")

# =========================
# PRETTY NAMES
# =========================
def pretty_logical_graph(name):
    base = os.path.splitext(os.path.basename(name))[0]
    m = re.match(r"clique(\d+)", base)
    if m:
        return f"C{m.group(1)}"
    m = re.match(r"bipartito(\d+)x(\d+)", base)
    if m:
        return f"K{m.group(1)},{m.group(2)}"
    return base

def pretty_physical_graph(name):
    base = os.path.splitext(os.path.basename(name))[0]
    m = re.match(r"zephyr(\d+)$", base)
    if m:
        return f"Zephyr (m={m.group(1)})"
    m = re.match(r"zephyr(\d+)_(\d+)_(\d+)", base)
    if m:
        return f"Zephyr (m={m.group(1)}, |V|={m.group(2)}, |E|={m.group(3)})"
    return base

# =========================
# LOAD SUMMARY
# =========================
with open(SUMMARY_FILE, "r") as f:
    summary_data = json.load(f)

results = []

# =========================
# LOOP ESPERIMENTI
# =========================
for exp_summary in summary_data:
    exp_id = exp_summary["experiment_id"]

    full_file = os.path.join(OUTPUT_DIR, str(exp_id), "full", f"experiment_{exp_id:03d}.json")
    reduced_file = os.path.join(OUTPUT_DIR, str(exp_id), "reduced", f"experiment_{exp_id:03d}.json")

    logical_graph = None
    physical_graph = None
    num_logical_nodes = None
    num_logical_edges = None
    num_physical_nodes = None
    num_physical_edges = None
    tempo_full_sat = None
    tempo_reduce_sat = None

    # =========================
    # LEGGO SAT (FULL)
    # =========================
    if os.path.isfile(full_file):
        with open(full_file, "r") as f:
            data = json.load(f)
        config = data.get("config", {})
        solver = data.get("solver", {})
        logical_info = data.get("logical_graph", {})
        physical_info = data.get("physical_graph", {})

        logical_graph = pretty_logical_graph(config.get("logical_graph", ""))
        physical_graph = pretty_physical_graph(config.get("physical_graph", ""))

        num_logical_nodes = logical_info.get("num_vertices")
        num_logical_edges = logical_info.get("num_edges")
        num_physical_nodes = physical_info.get("num_vertices")
        num_physical_edges = physical_info.get("num_edges")

        if solver.get("status") == "SAT":
            tempo_full_sat = solver.get("time_sat_solve")

    # =========================
    # LEGGO SAT (REDUCED)
    # =========================
    if os.path.isfile(reduced_file):
        with open(reduced_file, "r") as f:
            data = json.load(f)
        solver = data.get("solver", {})
        if solver.get("status") == "SAT":
            tempo_reduce_sat = solver.get("time_sat_solve")

    # =========================
    # LEGGO MINORMINER DAL SUMMARY (tempo solo embedding 1:1)
    # =========================
    full_mm = exp_summary.get("full", {})
    reduced_mm = exp_summary.get("reduced", {})

    tempo_mm_full = None
    tempo_mm_reduce = None
    att_full_1to1 = None
    att_red_1to1 = None

    # FULL
    full_best = full_mm.get("best_embedding")
    if full_best and full_mm.get("found_1to1"):
        tempo_mm_full = full_best.get("time_to_1to1")
        att_full_1to1 = full_best.get("attempts_to_1to1")

    # REDUCED
    reduced_best = reduced_mm.get("best_embedding")
    if reduced_best and reduced_mm.get("found_1to1"):
        tempo_mm_reduce = reduced_best.get("time_to_1to1")
        att_red_1to1 = reduced_best.get("attempts_to_1to1")

    results.append({
        "EXPERIMENT_ID": exp_id,
        "LOGICAL_GRAPH": logical_graph,
        "PHYSICAL_GRAPH": physical_graph,
        "NUM_LOGICAL_NODES": num_logical_nodes,
        "NUM_LOGICAL_EDGES": num_logical_edges,
        "NUM_PHYSICAL_NODES": num_physical_nodes,
        "NUM_PHYSICAL_EDGES": num_physical_edges,
        "TEMPO_MM_FULL": tempo_mm_full,
        "TEMPO_MM_REDUCE": tempo_mm_reduce,
        "TEMPO_FULL_SAT": tempo_full_sat,
        "TEMPO_REDUCE_SAT": tempo_reduce_sat,
        # TENTATIVI 1:1
        "MM_FULL_ATTEMPTS_TO_1TO1": att_full_1to1,
        "MM_REDUCED_ATTEMPTS_TO_1TO1": att_red_1to1,
        "MM_MAX_ATTEMPTS": exp_summary.get("max_attempts_allowed"),
    })

# =========================
# DATAFRAME + CSV
# =========================
df = pd.DataFrame(results)
df.to_csv(CSV_OUT, index=False)
print(f"CSV creato: {CSV_OUT}")
PLOT_DIR = os.path.dirname(CSV_OUT)

# =========================
# PLOT MINORMINER VS SAT (con barre non sovrapposte)
# =========================
for pg in df["PHYSICAL_GRAPH"].dropna().unique():
    df_pg = df[df["PHYSICAL_GRAPH"] == pg].copy()
    for col in ["TEMPO_MM_FULL", "TEMPO_MM_REDUCE", "TEMPO_FULL_SAT", "TEMPO_REDUCE_SAT"]:
        df_pg[col] = pd.to_numeric(df_pg[col], errors="coerce")

    # ETICHETTE con tentativi 1:1
    labels = []
    for _, r in df_pg.iterrows():
        parts = [str(r['LOGICAL_GRAPH'])]
        att_full = r["MM_FULL_ATTEMPTS_TO_1TO1"]
        att_red = r["MM_REDUCED_ATTEMPTS_TO_1TO1"]
        max_att = 100

        # Se max_att è None, usiamo "?" come segnaposto
        safe_max = int(max_att) if pd.notna(max_att) else "?"

        if pd.notna(att_full):
            parts.append(f"full:({int(att_full)}/{safe_max})")
        if pd.notna(att_red):
            parts.append(f"reduced:({int(att_red)}/{safe_max})")
        if pd.isna(att_full) and pd.isna(att_red):
            parts.append(f"(–/{safe_max})")

        labels.append("\n".join(parts))


    # =========================
    # Barre raggruppate
    # =========================
    x = np.arange(len(df_pg))  # posizioni dei gruppi
    n_bars = 4                 # barre per gruppo
    width = 0.2                # larghezza di ciascuna barra
    group_spacing = 0.2        # spazio extra tra gruppi

    fig, ax = plt.subplots(figsize=(18, 9))
    offsets = np.arange(n_bars) * width - (width * n_bars / 2) + width / 2

    bars_list = []
    cols = ["TEMPO_MM_FULL", "TEMPO_MM_REDUCE", "TEMPO_FULL_SAT", "TEMPO_REDUCE_SAT"]
    for i, col in enumerate(cols):
        bars = ax.bar(
            x * (n_bars*width + group_spacing) + offsets[i],
            df_pg[col],
            width,
            label=col
        )
        bars_list.append(bars)

    ax.set_xticks(x * (n_bars*width + group_spacing))
    ax.set_xticklabels(labels, rotation=0)
    ax.set_yscale("log")
    ax.set_ylabel("Tempo (s) [scala log]")
    ax.set_xlabel("Grafo logico")
    ax.set_title(f"Confronto Minorminer vs SAT\nGrafo fisico: {pg}")
    ax.legend()

    # Funzione autolabel
    def autolabel(bars):
        for bar in bars:
            h = bar.get_height()
            if h and not np.isnan(h):
                ax.annotate(
                    f"{h:.3f}",
                    (bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 6),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=9
                )
    for bars in bars_list:
        autolabel(bars)

    ax.margins(y=0.2)
    plt.tight_layout()

    safe_pg = re.sub(r"[^\w\-]+", "_", pg)
    plot_path = os.path.join(PLOT_DIR, f"confronto_tempi_{safe_pg}.png")
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"Grafico salvato: {plot_path}")
