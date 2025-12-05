import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

OUTPUTS_DIR = "outputs"
PLOTS_DIR = "plots"
os.makedirs(PLOTS_DIR, exist_ok=True)

def load_json(path):
    with open(path) as f:
        return json.load(f)

def collect_metrics(exp_id):
    exp_dir = os.path.join(OUTPUTS_DIR, exp_id)
    if not os.path.isdir(exp_dir):
        return None

    reduced_folder = os.path.join(exp_dir, "reduced")
    full_folder = os.path.join(exp_dir, "full")

    # Nome del file: experiment_XXX.json
    reduced_file = os.path.join(reduced_folder, f"experiment_{int(exp_id):03d}.json")
    full_file = os.path.join(full_folder, f"experiment_{int(exp_id):03d}.json")

    if not os.path.isfile(reduced_file) or not os.path.isfile(full_file):
        print(f"[WARN] File mancanti per experiment {exp_id}")
        return None

    reduced = load_json(reduced_file)
    full = load_json(full_file)

    return {
        "experiment_id": reduced["experiment_id"],
        "num_vars_reduced": reduced["sat_encoding"]["num_variables"],
        "num_vars_full": full["sat_encoding"]["num_variables"],
        "num_clauses_reduced": reduced["sat_encoding"]["num_clauses"],
        "num_clauses_full": full["sat_encoding"]["num_clauses"],
        "time_sat_reduced": reduced["solutions"][0]["sat_time"] if reduced["solutions"] else None,
        "time_sat_full": full["solutions"][0]["sat_time"] if full["solutions"] else None,
    }

# Raccogli metriche da tutti gli esperimenti
all_metrics = []
for exp_id in sorted(os.listdir(OUTPUTS_DIR)):
    metrics = collect_metrics(exp_id)
    if metrics:
        all_metrics.append(metrics)

df = pd.DataFrame(all_metrics)
df = df.sort_values("experiment_id")

sns.set_style("whitegrid")  # Migliore stile per i grafici

# ---------- Grafico 1: Numero di variabili ----------
plt.figure(figsize=(10,6))
df_plot_vars = df.melt(id_vars="experiment_id",
                       value_vars=["num_vars_reduced", "num_vars_full"],
                       var_name="variant", value_name="num_variables")

sns.barplot(
    data=df_plot_vars,
    x="experiment_id",
    y="num_variables",
    hue="variant",
    palette=["skyblue", "dodgerblue"],
    errorbar=None
)
plt.title("Numero di Variabili: FULL vs REDUCED")
plt.ylabel("Numero di variabili")
plt.xlabel("Experiment ID")
plt.xticks(rotation=0)
plt.yticks(np.arange(0, df_plot_vars["num_variables"].max() + 10, step=max(1, df_plot_vars["num_variables"].max() // 10)))
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "num_variables_comparison.png"))
plt.close()

# ---------- Grafico 2: Numero di clausole ----------
plt.figure(figsize=(10,6))
df_plot_clauses = df.melt(id_vars="experiment_id",
                          value_vars=["num_clauses_reduced", "num_clauses_full"],
                          var_name="variant", value_name="num_clauses")

# Forza tipo intero
df_plot_clauses["num_clauses"] = df_plot_clauses["num_clauses"].astype(int)

sns.barplot(
    data=df_plot_clauses,
    x="experiment_id",
    y="num_clauses",
    hue="variant",
    palette=["lightgreen", "green"],
    errorbar=None
)
plt.title("Numero di Clausole: FULL vs REDUCED")
plt.ylabel("Numero di clausole")
plt.xlabel("Experiment ID")
plt.xticks(rotation=0)

# Tick y interi e più leggibili
ymax = df_plot_clauses["num_clauses"].max()
yticks = np.linspace(0, ymax, num=10, dtype=int)
plt.yticks(yticks)

plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "num_clauses_comparison.png"))
plt.close()

# ---------- Grafico 3: Tempo SAT ----------
plt.figure(figsize=(10,6))
df_plot_time = df.melt(id_vars="experiment_id",
                       value_vars=["time_sat_reduced", "time_sat_full"],
                       var_name="variant", value_name="time_sec")

sns.barplot(
    data=df_plot_time,
    x="experiment_id",
    y="time_sec",
    hue="variant",
    palette=["skyblue", "dodgerblue"],
    errorbar=None
)
plt.title("Tempo SAT: FULL vs REDUCED")
plt.ylabel("SAT Time (s)")
plt.xlabel("Experiment ID")
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "time_sat_comparison.png"))
plt.close()

print(f"[INFO] Grafici salvati in '{PLOTS_DIR}'")
