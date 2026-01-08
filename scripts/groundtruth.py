import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# --- CONFIG ---
OUTPUT_DIR = "outputs"
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "minorminer_summary.json")

# --- CARICAMENTO RIASSUNTIVO MINORMINER ---
with open(SUMMARY_FILE, "r") as f:
    summary_data = json.load(f)

# --- ORGANIZZA I DATI PER ESPERIMENTO E MODALITÀ ---
results_dict = {}
for entry in summary_data:
    exp_id = entry["experiment_id"]
    mode = entry["mode"]
    
    if exp_id not in results_dict:
        results_dict[exp_id] = {}
    
    results_dict[exp_id][mode] = entry

# --- PREPARA LA LISTA DEI RISULTATI ---
results = []

for exp_id, modes in results_dict.items():
    # Minorminer
    full_mm = modes.get("full", {})
    reduced_mm = modes.get("reduced", {})

    tempo_mm_full = full_mm.get("time_seconds")
    success_mm_full = full_mm.get("success")
    tempo_mm_reduce = reduced_mm.get("time_seconds")
    success_mm_reduce = reduced_mm.get("success")
    num_logical = full_mm.get("num_logical_nodes")
    num_physical_full = full_mm.get("num_physical_nodes")
    num_physical_reduce = reduced_mm.get("num_physical_nodes")
    max_chain_full = full_mm.get("max_chain_length")
    max_chain_reduce = reduced_mm.get("max_chain_length")

    # Percorsi ai file SAT (Full e Reduced)
    full_file = os.path.join(OUTPUT_DIR, str(exp_id), "full", f"experiment_{exp_id:03d}.json")
    reduced_file = os.path.join(OUTPUT_DIR, str(exp_id), "reduced", f"experiment_{exp_id:03d}.json")

    # Inizializza valori SAT
    tempo_full = None
    success_full = None
    tempo_reduce = None
    success_reduce = None
    logical_graph_name = f"logical_{exp_id}"
    physical_graph_name = f"physical_{exp_id}"

    # Carica Full SAT
    if os.path.isfile(full_file):
        with open(full_file, "r") as f:
            full_data = json.load(f)
            solver_full = full_data.get("solver", {})
            tempo_full = solver_full.get("time_sat_solve")
            success_full = solver_full.get("status")
            config = full_data.get("config", {})
            logical_graph_name = config.get("logical_graph", logical_graph_name)
            physical_graph_name = config.get("physical_graph", physical_graph_name)

    # Carica Reduced SAT
    if os.path.isfile(reduced_file):
        with open(reduced_file, "r") as f:
            red_data = json.load(f)
            solver_red = red_data.get("solver", {})
            tempo_reduce = solver_red.get("time_sat_solve")
            success_reduce = solver_red.get("status")

    results.append({
        "EXPERIMENT_ID": exp_id,
        "LOGICAL_GRAPH": logical_graph_name,
        "PHYSICAL_GRAPH": physical_graph_name,
        "NUM_LOGICAL_NODES": num_logical,
        "NUM_PHYSICAL_NODES_FULL": num_physical_full,
        "NUM_PHYSICAL_NODES_REDUCE": num_physical_reduce,
        "SUCCESS_MM_FULL": success_mm_full,
        "TEMPO_MM_FULL": tempo_mm_full,
        "MAX_CHAIN_MM_FULL": max_chain_full,
        "SUCCESS_MM_REDUCE": success_mm_reduce,
        "TEMPO_MM_REDUCE": tempo_mm_reduce,
        "MAX_CHAIN_MM_REDUCE": max_chain_reduce,
        "SUCCESS_FULL_SAT": success_full,
        "TEMPO_FULL_SAT": tempo_full,
        "SUCCESS_REDUCE_SAT": success_reduce,
        "TEMPO_REDUCE_SAT": tempo_reduce
    })

# --- CREA DATAFRAME ---
df = pd.DataFrame(results)

# --- SALVA CSV ---
csv_path = os.path.join(OUTPUT_DIR, "embedding_times_summary.csv")
df.to_csv(csv_path, index=False)

print(f"Tabella creata con successo: {csv_path}")
print(df)

# --- PLOTTING TEMPI ---
df_plot = df.copy()
x = np.arange(len(df_plot)) * 2
width = 0.2

fig, ax = plt.subplots(figsize=(16, 8))

bars_mm_full = ax.bar(x - width, df_plot["TEMPO_MM_FULL"], width, label="Minorminer Full", color="mediumseagreen")
bars_mm_reduce = ax.bar(x, df_plot["TEMPO_MM_REDUCE"], width, label="Minorminer Reduced", color="green")
bars_full_sat = ax.bar(x + width, df_plot["TEMPO_FULL_SAT"], width, label="Full SAT", color="lightblue")
bars_reduce_sat = ax.bar(x + 2*width, df_plot["TEMPO_REDUCE_SAT"], width, label="Reduced SAT", color="mediumblue")

ax.set_yscale('log')
ax.set_ylabel("Tempo (s) [scala log]")
ax.set_xlabel("ID esperimento")
ax.set_title("Confronto tempi Minorminer e SAT (Full vs Reduced)")
ax.set_xticks(x + width/2)
ax.set_xticklabels(df_plot["EXPERIMENT_ID"])
ax.legend()

# Etichette sopra le barre
def autolabel(bars):
    for bar in bars:
        height = bar.get_height()
        if not np.isnan(height):
            ax.annotate(f'{height:.4f}',
                        xy=(bar.get_x() + bar.get_width()/2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)

for bars in [bars_mm_full, bars_mm_reduce, bars_full_sat, bars_reduce_sat]:
    autolabel(bars)

plt.tight_layout()
plt.show()


