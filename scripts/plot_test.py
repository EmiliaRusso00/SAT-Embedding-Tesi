import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
import yaml  # Per leggere la lista degli esperimenti

# =========================
# CONFIG
# =========================
OUTPUT_DIR = "outputs"
CONFIG_FILE = "config.yaml"  # file YAML con gli esperimenti
CSV_OUT = os.path.join(OUTPUT_DIR, "embedding_times_comparison.csv")

# =========================
# FUNZIONI UTILI
# =========================
def pretty_logical_graph(path):
    base = os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"clique(\d+)", base)
    if m: return f"C{m.group(1)}"
    m = re.match(r"bipartito(\d+)x(\d+)", base)
    if m: return f"K{m.group(1)},{m.group(2)}"
    return base

def pretty_physical_graph(path):
    base = os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"zephyr(\d+)$", base)
    if m: return f"Zephyr (m={m.group(1)})"
    m = re.match(r"zephyr(\d+)_(\d+)_(\d+)", base)
    if m: return f"Zephyr (m={m.group(1)}, |V|={m.group(2)}, |E|={m.group(3)})"
    return base

def load_json(file_path):
    if os.path.isfile(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return None

# =========================
# LEGGO CONFIG ESPERIMENTI
# =========================
with open(CONFIG_FILE, "r") as f:
    cfg = yaml.safe_load(f)

experiments = cfg.get("experiments", [])

results = []

# =========================
# LOOP ESPERIMENTI
# =========================
for exp in experiments:
    exp_id = exp["id"]
    logical_graph = pretty_logical_graph(exp["logical_graph"])
    physical_graph = pretty_physical_graph(exp["physical_graph"])

    for mode in ["full", "reduced"]:
        exp_dir = os.path.join(OUTPUT_DIR, str(exp_id), mode)
        mm_file = os.path.join(exp_dir, "minorminer_result.json")
        sat_file = os.path.join(exp_dir, "sat_minorminer_result.json")
        sat_allowed_file = os.path.join(exp_dir, "sat_minorminer_result_allowed.json")

        mm_data = load_json(mm_file)
        sat_data = load_json(sat_file)
        sat_allowed_data = load_json(sat_allowed_file)

        # Salta esperimenti falliti
        if mm_data is None or not mm_data.get("success", False):
            continue

        results.append({
            "EXPERIMENT_ID": exp_id,
            "LOGICAL_GRAPH": logical_graph,
            "PHYSICAL_GRAPH": physical_graph,
            "MODE": mode,
            "TEMPO_MM": mm_data.get("time_seconds"),
            "TEMPO_MM_USED": mm_data.get("num_physical_used"),
            "TEMPO_MM_CHAIN": mm_data.get("max_chain_length"),
            "TEMPO_SAT": sat_data.get("time_seconds") if sat_data and sat_data.get("success") else None,
            "TEMPO_SAT_USED": sat_data.get("num_physical_used") if sat_data and sat_data.get("success") else None,
            "TEMPO_SAT_CHAIN": sat_data.get("max_chain_length") if sat_data and sat_data.get("success") else None,
            "TEMPO_SAT_ALLOWED": sat_allowed_data.get("time_seconds") if sat_allowed_data and sat_allowed_data.get("success") else None,
            "TEMPO_SAT_ALLOWED_USED": sat_allowed_data.get("num_physical_used") if sat_allowed_data and sat_allowed_data.get("success") else None,
            "TEMPO_SAT_ALLOWED_CHAIN": sat_allowed_data.get("max_chain_length") if sat_allowed_data and sat_allowed_data.get("success") else None
        })

# =========================
# CREO DATAFRAME + CSV
# =========================
df = pd.DataFrame(results)
df.to_csv(CSV_OUT, index=False)
print(f"CSV creato: {CSV_OUT}")

# =========================
# PLOT COMPARATIVO TEMPI
# =========================
for pg in df["PHYSICAL_GRAPH"].unique():
    df_pg = df[df["PHYSICAL_GRAPH"] == pg].copy()

    for mode in ["full", "reduced"]:
        df_mode = df_pg[df_pg["MODE"] == mode]
        if df_mode.empty:
            continue

        x = np.arange(len(df_mode))
        width = 0.25

        fig, ax = plt.subplots(figsize=(16,6))

        bars1 = ax.bar(x - width, df_mode["TEMPO_MM"], width, label="Minorminer standard")
        bars2 = ax.bar(x, df_mode["TEMPO_SAT"], width, label="Minorminer + SAT")
        bars3 = ax.bar(x + width, df_mode["TEMPO_SAT_ALLOWED"], width, label="Minorminer + SAT Allowed")

        ax.set_xticks(x)
        ax.set_xticklabels(df_mode["LOGICAL_GRAPH"])
        ax.set_ylabel("Tempo embedding (s)")
        ax.set_xlabel("Grafo logico")
        ax.set_title(f"Confronto tempi: Minorminer standard vs +SAT vs +SAT Allowed - {mode} - {pg}")
        ax.legend()

        # Annotazioni sopra le barre
        for i, bar in enumerate(bars1):
            h = bar.get_height()
            if h is not None:
                used = df_mode.iloc[i]["TEMPO_MM_USED"]
                chain = df_mode.iloc[i]["TEMPO_MM_CHAIN"]
                ax.annotate(f"{h:,.6f}\nU:{used}, C:{chain}",
                            (bar.get_x()+bar.get_width()/2, h),
                            ha='center', va='bottom', fontsize=8)

        for i, bar in enumerate(bars2):
            h = bar.get_height()
            if h is not None:
                used = df_mode.iloc[i]["TEMPO_SAT_USED"]
                chain = df_mode.iloc[i]["TEMPO_SAT_CHAIN"]
                ax.annotate(f"{h:,.6f}\nU:{used}, C:{chain}",
                            (bar.get_x()+bar.get_width()/2, h),
                            ha='center', va='bottom', fontsize=8)

        for i, bar in enumerate(bars3):
            h = bar.get_height()
            if h is not None:
                used = df_mode.iloc[i]["TEMPO_SAT_ALLOWED_USED"]
                chain = df_mode.iloc[i]["TEMPO_SAT_ALLOWED_CHAIN"]
                ax.annotate(f"{h:,.6f}\nU:{used}, C:{chain}",
                            (bar.get_x()+bar.get_width()/2, h),
                            ha='center', va='bottom', fontsize=8)

        plt.tight_layout()
        plot_path = os.path.join(OUTPUT_DIR, f"confronto_{pg}_{mode}.png")
        plt.savefig(plot_path, dpi=300)
        plt.close()
        print(f"Grafico salvato: {plot_path}")
