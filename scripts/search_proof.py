import os
import json
from collections import defaultdict
import sys
import argparse
from contextlib import redirect_stdout

# Import necessari per ricreare cnf_generator
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from parser import read_graph, read_graph_json
from cnf_generator import CNFGenerator


# ------------------------------------------------------------
# 0. Costruzione path della proof
# ------------------------------------------------------------
def get_proof_path(exp_dir, exp_id, mode):
    if mode not in ("full", "reduced"):
        raise ValueError("mode deve essere 'full' o 'reduced'")

    proof_name = f"proof_{exp_id}_{mode}.txt"
    proof_path = os.path.join(exp_dir, str(exp_id), mode, proof_name)

    if not os.path.exists(proof_path):
        raise FileNotFoundError(f"Proof non trovata: {proof_path}")

    return proof_path


# ------------------------------------------------------------
# 1. Estrazione delle clausole unitarie
# ------------------------------------------------------------
def extract_unit_literals(proof_path):
    unit_literals = []

    with open(proof_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("d"):
                continue

            tokens = line.split()
            if tokens[-1] != "0":
                continue

            if len(tokens) == 2:
                try:
                    unit_literals.append(int(tokens[0]))
                except ValueError:
                    pass

    return unit_literals


# ------------------------------------------------------------
# 2. Decodifica letterali SAT → (logico, fisico)
# ------------------------------------------------------------
def decode_unit_literals(unit_literals, inv_var_map):
    decoded = []

    for lit in unit_literals:
        var = abs(lit)
        if var not in inv_var_map:
            continue

        logical, physical = inv_var_map[var]
        decoded.append((logical, physical, lit > 0))

    return decoded


# ------------------------------------------------------------
# 3. Stato di embedding per nodo logico
# ------------------------------------------------------------
def build_logical_state(decoded, logical_nodes, physical_nodes):
    logical_state = {
        i: {
            "allowed": set(physical_nodes),
            "forbidden": set(),
            "forced": set()
        }
        for i in logical_nodes
    }

    for i, a, value in decoded:
        if value:
            logical_state[i]["forced"].add(a)
            logical_state[i]["allowed"] = {a}
        else:
            logical_state[i]["forbidden"].add(a)
            logical_state[i]["allowed"].discard(a)

    return logical_state


# ------------------------------------------------------------
# 4. Classificazione nodi logici
# ------------------------------------------------------------
def classify_logical_nodes(logical_state):
    result = {
        "impossible": [],
        "overconstrained": [],
        "forced": []
    }

    for i, st in logical_state.items():
        if len(st["allowed"]) == 0:
            result["impossible"].append(i)
        elif len(st["forced"]) > 1:
            result["overconstrained"].append(i)
        elif len(st["allowed"]) == 1:
            result["forced"].append(i)

    return result


# ------------------------------------------------------------
# 5. Conflitti sui nodi fisici
# ------------------------------------------------------------
def find_physical_conflicts(decoded):
    physical_usage = defaultdict(set)

    for i, a, value in decoded:
        if value:
            physical_usage[a].add(i)

    return {
        a: list(nodes)
        for a, nodes in physical_usage.items()
        if len(nodes) > 1
    }


# ------------------------------------------------------------
# 6. Conflitti topologici (edge consistency)
# ------------------------------------------------------------
def find_edge_conflicts(logical_state, G_log):
    conflicts = []

    for i, st in logical_state.items():
        if len(st["allowed"]) == 0:
            for j in G_log.neighbors(i):
                if len(logical_state[j]["allowed"]) <= 1:
                    conflicts.append((i, j))

    return conflicts


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analizza una proof UNSAT per embedding.")
    parser.add_argument("exp_id", type=int, help="ID dell'esperimento")
    parser.add_argument("mode", choices=["full", "reduced"], help="Modalità: full o reduced")
    args = parser.parse_args()

    exp_dir = "outputs"
    exp_id = args.exp_id
    mode = args.mode

    analysis_dir = os.path.join(exp_dir, str(exp_id), mode)
    os.makedirs(analysis_dir, exist_ok=True)

    analysis_txt_path = os.path.join(analysis_dir, "unsat_analysis.txt")

    with open(analysis_txt_path, "w") as f, redirect_stdout(f):

        print("=" * 70)
        print(f"UNSAT ANALYSIS | Experiment {exp_id} | Mode {mode}")
        print("=" * 70)

        exp_json_path = os.path.join(
            exp_dir, str(exp_id), mode, f"experiment_{exp_id:03d}.json"
        )
        if not os.path.exists(exp_json_path):
            print(f"Errore: file esperimento non trovato: {exp_json_path}")
            sys.exit(1)

        with open(exp_json_path, "r") as f_json:
            exp_data = json.load(f_json)

        cfg = exp_data["config"]

        # Carica grafi
        G_log = read_graph(cfg["logical_graph"])

        if mode == "full":
            G_phys = read_graph(cfg["physical_graph"])
            cnf_gen = CNFGenerator(
                G_log=G_log,
                G_phys=G_phys,
                skip_reduction=True
            )
        else:
            reduced_phys_path = cfg.get("reduce_physical_graph")
            if reduced_phys_path and os.path.exists(reduced_phys_path):
                G_phys, _ = read_graph_json(reduced_phys_path)
            else:
                G_phys = read_graph(cfg["physical_graph"])

            reduced_id_json = os.path.join(
                exp_dir, str(exp_id), "reduced",
                f"reduced_physical_{exp_id}.json"
            )
            with open(reduced_id_json, "r") as rf:
                reduced_data = json.load(rf)

            physical_center = reduced_data["metadata"]["physical_center"]
            print(f"[INFO] Centro fisico letto da JSON: {physical_center}")

            cnf_gen = CNFGenerator(
                G_log=G_log,
                G_phys=G_phys,
                skip_reduction=False,
                physical_center=physical_center
            )

        proof_path = get_proof_path(exp_dir, exp_id, mode)
        print(f"\nAnalizzando proof: {proof_path}")

        unit_literals = extract_unit_literals(proof_path)
        print(f"\nClausole unitarie estratte: {len(unit_literals)}")
        print("Esempi:", unit_literals[:10])

        decoded = decode_unit_literals(unit_literals, cnf_gen.inv_var_map)
        print(f"\nCoppie decodificate: {len(decoded)}")
        print("Esempi:", decoded[:10])

        logical_state = build_logical_state(
            decoded,
            cnf_gen.logical_nodes,
            cnf_gen.physical_nodes
        )

        print("\n=== Stato logico per nodo ===")
        for log_node in sorted(logical_state.keys()):
            st = logical_state[log_node]
            st["forbidden"].update(
                set(cnf_gen.physical_nodes) - st["allowed"] - st["forced"]
            )

            print(f" Nodo logico {log_node}:")
            print(f"   Allowed  : {sorted(st['allowed'])}")
            print(f"   Forbidden: {sorted(st['forbidden'])}")
            print(f"   Forced   : {sorted(st['forced'])}")

        classification = classify_logical_nodes(logical_state)
        print("\n=== Classificazione ===")
        print(" Impossibili     :", classification["impossible"])
        print(" Overconstrained :", classification["overconstrained"])
        print(" Forzati         :", classification["forced"])

            # --- Nuovo blocco: estrazione clausole forzate DIMACS ---
        # --- Nuovo blocco: estrazione clausole forzate DIMACS (anche allowed singolo) ---
        forced_dimacs = []
        for log_node, st in logical_state.items():
            # Se c'è un solo allowed, forzalo
            if len(st["allowed"]) == 1:
                phys_node = next(iter(st["allowed"]))
                var_id = cnf_gen.x(log_node, phys_node)
                forced_dimacs.append((var_id, log_node, phys_node))
        if forced_dimacs:
            print("\n=== Clausole DIMACS forzate (allowed singolo) ===")
            for var_id, log_node, phys_node in forced_dimacs:
                print(f"{var_id} 0   # x({log_node},{phys_node})")

        physical_conflicts = find_physical_conflicts(decoded)
        edge_conflicts = find_edge_conflicts(logical_state, G_log)

        print("\n=== Conflitti fisici ===")
        if physical_conflicts:
            for phys, logs in physical_conflicts.items():
                print(f" Nodo fisico {phys}: logici {logs}")
        else:
            print(" Nessuno")

        print("\n=== Conflitti di edge ===")
        if edge_conflicts:
            for i, j in edge_conflicts:
                print(f" Arco logico ({i},{j}) non rispettabile")
        else:
            print(" Nessuno")

        print("\n=== FINE ANALISI ===")
