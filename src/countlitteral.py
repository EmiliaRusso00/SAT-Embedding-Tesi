# Voglio leggere la proof del file 21 ridotto e convertire i numeri in coppie nodo logico, nodo fisico
# Tenendo conto che le clasuole con la d sono quelle eliminate dal solver (quindi da non prendere in considerazione)
# Le altre clasuole sono quelle che compongono la proof e voglio capire quali portano alla contraddizione
# Dato che il grafo logico è una CLIQUE 5 e il grafo fisico è un pegaso con m=2 e grafo ridotto contenuto in outputs/21/reduced/reduced_physical_21.json
import json
import os
import networkx as nx
from cnf_generator import CNFGenerator

# -------------------------
# Parametri esperimento
# -------------------------
EXP_ID = 21
REDUCED_PATH = f"outputs/{EXP_ID}/reduced/reduced_physical_{EXP_ID}.json"
PROOF_PATH = f"outputs/{EXP_ID}/reduced/proof_{EXP_ID}.txt"
OUTPUT_PATH = f"outputs/{EXP_ID}/proof_converted_{EXP_ID}.txt"

# -------------------------
# 1. Grafo logico: clique 5
# -------------------------
G_log = nx.complete_graph(5)

# -------------------------
# 2. Grafo fisico: dal JSON
# -------------------------
with open(REDUCED_PATH, "r") as f:
    reduced_json = json.load(f)

G_phys = nx.Graph()
G_phys.add_nodes_from(reduced_json["nodes"])
G_phys.add_edges_from([tuple(e) for e in reduced_json["edges"]])

# -------------------------
# 3. Genera CNF generator per mapping variabile -> (logico,fisico)
# -------------------------
cnf_gen = CNFGenerator(G_log, G_phys, exp_dir=f"outputs/{EXP_ID}", exp_id=EXP_ID, skip_reduction=True)
cnf_gen.generate()  # genera clausole e mapping

# -------------------------
# 4. Leggi proof dal file
# -------------------------
proof_clauses = []
with open(PROOF_PATH, "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('c'):
            continue
        # 'd' indica clausola eliminata → skip
        if line.startswith('d'):
            continue
        # parse literals
        lits = [int(x) for x in line.split() if x != '0']
        if lits:
            proof_clauses.append(lits)

# -------------------------
# 5. Converti numeri in coppie (nodo logico, nodo fisico) preservando segno
# -------------------------
rev_var_map = {v: k for k, v in cnf_gen.var_map.items()}

converted_lines = []
for clause in proof_clauses:
    clause_items = []
    for lit in clause:
        var = abs(lit)
        sign = "-" if lit < 0 else ""
        if var in rev_var_map:
            ln, pn = rev_var_map[var]
            clause_items.append(f"{sign}({ln},{pn})")
        else:
            clause_items.append(f"{sign}(unknown,unknown)")
    converted_lines.append(' '.join(clause_items))

# -------------------------
# 6. Scrivi su file TXT
# -------------------------
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w") as f:
    for line in converted_lines:
        f.write(line + "\n")

print(f"[INFO] Proof convertita e salvata in: {OUTPUT_PATH}")




