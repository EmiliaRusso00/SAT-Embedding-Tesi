# cnf_generator_improved.py
from itertools import combinations
from collections import deque
import networkx as nx
import json
import os
import math


class CNFGenerator:

    def __init__(self, G_log, G_phys, G_log_json=None, G_phys_json=None,
                 allow_shared_physical=False, exp_dir=None, exp_id=0,
                 check_treewidth=True, skip_reduction=False):
        """
        G_log: grafo logico (NetworkX)
        G_phys: grafo fisico (NetworkX)
        G_log_json, G_phys_json: opzionali metadata (dict o graph-like)
        allow_shared_physical: se True permette condivisione di nodi fisici
        exp_dir, exp_id: per salvare JSON del sotto-grafo fisico ridotto
        check_treewidth: se False ignora il controllo di treewidth
        """
        self.G_log = G_log
        self.G_phys_original = G_phys
        self.allow_shared_physical = allow_shared_physical
        self.G_log_json = G_log_json
        self.G_phys_json = G_phys_json
        self.exp_dir = exp_dir
        self.exp_id = exp_id
        self.check_treewidth = check_treewidth
        self.skip_reduction = skip_reduction

        # flags e motivi di rifiuto
        self.embeddable = True
        self.reject_reasons = []

        # -------------------------
        # Estrai sotto-grafo fisico centrato (riduzione preventiva)
        # -------------------------
        if self.skip_reduction:
            print("[INFO] Variante FULL: nessuna riduzione del grafo fisico.")
            self.G_phys = self.G_phys_original.copy()
            self.center_node = None
            self.logical_center = None
            self.phys_radius = None
        else:
            print("[INFO] Variante REDUCED: estrazione sottografo fisico centrato.")
            self.G_phys, self.center_node, self.logical_center, self.phys_radius = \
                self._extract_physical_subgraph(self.G_phys_original, self.G_log)
        # -------------------------
        # Esegui controlli di impossibilità strutturale
        # -------------------------
        try:
            self._precheck_embedding(self.G_log, self.G_phys)
        except Exception as e:
            self.embeddable = False
            self.reject_reasons.append(f"Errore durante precheck: {e}")
            print(f"[WARN] Errore durante precheck embedding: {e}")

        # -------------------------
        # Salva JSON del sotto-grafo fisico ridotto se possibile
        # -------------------------
        if self.G_phys is not None and len(self.G_phys.nodes()) and self.exp_dir:
            try:
                self._save_reduced_phys_json()
            except Exception as e:
                print(f"[WARN] Non sono riuscito a salvare reduced JSON: {e}")

        # -------------------------
        # Ordinamento dei nodi
        # -------------------------
        self.logical_nodes = list(sorted(G_log.nodes()))
        self.physical_nodes = list(sorted(self.G_phys.nodes()))

        self.n = len(self.logical_nodes)
        self.m = len(self.physical_nodes)

        # Mappa variabili SAT: (log_node, phys_node) → id univoco
        self.var_map = {}
        vid = 1
        for i in self.logical_nodes:
            for a in self.physical_nodes:
                self.var_map[(i, a)] = vid
                vid += 1

        self.num_vars = vid - 1
        self.clauses = []
        self.clause_type = []

    # -------------------------
    # Prechecks di embeddability
    # -------------------------
    def _precheck_embedding(self, G_log, G_phys):
        n_log = len(G_log)
        n_phys = len(G_phys)
        if n_phys < n_log:
            self.embeddable = False
            self.reject_reasons.append(f"|V_phys|={n_phys} < |V_log|={n_log}")
            print(f"[PRUNE] {self.reject_reasons[-1]}")
            return

        max_log_deg = max(dict(G_log.degree()).values(), default=0)
        max_phys_deg = max(dict(G_phys.degree()).values(), default=0)
        if max_log_deg > max_phys_deg:
            self.embeddable = False
            self.reject_reasons.append(f"Δ(G_log)={max_log_deg} > Δ(G_phys)={max_phys_deg}")
            print(f"[PRUNE] {self.reject_reasons[-1]}")
            return

        try:
            if nx.is_connected(G_log):
                comp_sizes = [len(c) for c in nx.connected_components(G_phys)]
                max_comp = max(comp_sizes) if comp_sizes else 0
                if max_comp < n_log:
                    self.embeddable = False
                    self.reject_reasons.append(f"La più grande componente di G_phys ha solo {max_comp} nodi < |V_log|={n_log}")
                    print(f"[PRUNE] {self.reject_reasons[-1]}")
                    return
        except Exception:
            pass

        if len(self.G_phys) < len(G_log):
            self.embeddable = False
            self.reject_reasons.append(f"Sotto-grafo fisico ridotto ha {len(self.G_phys)} nodi < |V_log|={len(G_log)}")
            print(f"[PRUNE] {self.reject_reasons[-1]}")
            return

        if self.check_treewidth:
            try:
                lb_log = self._approx_treewidth_lower_bound(G_log)
                ub_phys = self._approx_treewidth_upper_bound(G_phys)
                print(f"[INFO] Treewidth bounds: LB_log={lb_log}, UB_phys={ub_phys}")
                if lb_log > ub_phys:
                    self.embeddable = False
                    self.reject_reasons.append(f"LB_treewidth(G_log)={lb_log} > UB_treewidth(G_phys)={ub_phys}")
                    print(f"[PRUNE] {self.reject_reasons[-1]}")
                    return
            except Exception as e:
                print(f"[WARN] Errore treewidth: {e}")

        self.embeddable = True

    # -------------------------
    # Euristiche Treewidth
    # -------------------------
    def _approx_treewidth_lower_bound(self, G):
        try:
            clique_num = nx.graph_clique_number(G)
        except Exception:
            clique_num = 1
        try:
            core = nx.core_number(G)
            degeneracy = max(core.values()) if core else 0
        except Exception:
            degeneracy = 0
        return max(clique_num - 1, degeneracy)

    def _approx_treewidth_upper_bound(self, G):
        H = G.copy()
        if len(H) == 0:
            return 0
        max_width_seen = 0
        while H.number_of_nodes() > 0:
            best_node = None
            best_fill = None
            best_deg = None
            for v in list(H.nodes()):
                neigh = set(H.neighbors(v))
                possible = len(neigh) * (len(neigh) - 1) // 2
                existing = H.subgraph(neigh).number_of_edges() if neigh else 0
                fill_in = possible - existing
                deg_v = len(neigh)
                if best_fill is None or fill_in < best_fill or (fill_in == best_fill and deg_v < best_deg):
                    best_node = v
                    best_fill = fill_in
                    best_deg = deg_v
            bag_size = best_deg if best_deg is not None else 0
            max_width_seen = max(max_width_seen, bag_size)
            neigh = list(H.neighbors(best_node))
            for i in range(len(neigh)):
                for j in range(i+1, len(neigh)):
                    if not H.has_edge(neigh[i], neigh[j]):
                        H.add_edge(neigh[i], neigh[j])
            H.remove_node(best_node)
        return max_width_seen

    # -------------------------
    # Estrazione sotto-grafo fisico centrato
    # -------------------------
    def _extract_physical_subgraph(self, G_phys, G_log):
        if len(G_phys) == 0:
            print("[INFO]: Grafo fisico vuoto, nessuna riduzione possibile.")
            return G_phys.copy(), None, None, 0
        
        # -------------------------
        # Componente più grande del grafo fisico
        # -------------------------
        components = list(nx.connected_components(G_phys))
        if not components:
            print("[INFO] Nessuna componente connessa trovata.")
            return G_phys.copy(), None, None, 0
        
        comp = max(components, key=len)
        G_comp = G_phys.subgraph(comp).copy()
        print(f"[INFO] Componente fisica più grande con {len(G_comp)} nodi selezionata.")
        
        # -------------------------
        # Centro logico e grado richiesto
        # -------------------------
        try:
            logical_center = nx.center(G_log)[0]
        except Exception:
            logical_center = max(G_log.degree(), key=lambda x: x[1])[0]
        min_degree_required = G_log.degree(logical_center)
        
        print(f"[INFO] Nodo centrale logico: {logical_center} con grado {min_degree_required}")
        
        # -------------------------
        # Centro fisico con grado compatibile
        # -------------------------
        try:
            physical_centers = nx.center(G_comp)
            candidate_centers = [n for n in physical_centers if G_comp.degree(n) >= min_degree_required]
        except Exception:
            candidate_centers = [n for n, d in G_comp.degree() if d >= min_degree_required]
        
        if candidate_centers:
            physical_center = candidate_centers[0]
        else:
            high_deg_nodes = [n for n, d in G_comp.degree() if d >= min_degree_required]
            physical_center = high_deg_nodes[0] if high_deg_nodes else max(G_comp.degree(), key=lambda x: x[1])[0]

        print(f"[INFO] Nodo centrale fisico selezionato: {physical_center} con grado {G_comp.degree(physical_center)}")
        
        # -------------------------
        # Diametro logico = raggio fisico
        # -------------------------
        if len(G_log) > 1:
            d_log = nx.diameter(G_log)
        else:
            d_log = 0

        print(f"[INFO] Diametro logico stimato: {d_log}")
        
        # -------------------------
        # BFS dal centro fisico e selezione nodi entro distanza <= d_log
        # -------------------------
        distances = nx.single_source_shortest_path_length(G_comp, physical_center)

        R = math.ceil(d_log/2)   # raggio fisico = diametro logico
        chosen_nodes = [n for n, dist in distances.items() if dist <= R]

        G_sub = G_comp.subgraph(chosen_nodes).copy()

        if len(G_sub) < len(G_log):
            print(f"[WARN] Sottografo ridotto ha {len(G_sub)} nodi < |V_log|={len(G_log)}; potrebbe non essere embeddabile senza espansione.")
            
        print(f"[INFO] Sottografo fisico finale: {len(G_sub)} nodi selezionati entro distanza {R}.")
        print(f"[INFO] Nodo centrale fisico: {physical_center}, nodo centrale logico: {logical_center}")

        return G_sub, physical_center, logical_center, R


    # -------------------------
    # Salvataggio JSON
    # -------------------------
    def _save_reduced_phys_json(self):
        import os, json

        # Recupera i metadati esistenti se presenti
        metadata = {}
        if isinstance(self.G_phys_json, dict):
            metadata = self.G_phys_json.get("metadata", {})
        elif hasattr(self.G_phys_json, "graph"):
            try:
                metadata = dict(self.G_phys_json.graph)
            except Exception:
                metadata = {}

        # Aggiungi le informazioni sul centro fisico e logico
        metadata.update({
        "physical_center": self.center_node,
        "physical_center_degree": self.G_phys.degree(self.center_node) if self.center_node is not None else None,
        "logical_center": self.logical_center,
        "logical_center_degree": self.G_log.degree(self.logical_center) if self.logical_center is not None else None,
        "num_logical_nodes": len(self.G_log),
        "num_physical_nodes": len(self.G_phys)
    })
        reduced_nodes = list(self.G_phys.nodes())
        reduced_edges = [list(e) for e in self.G_phys.edges()]
        reduced_json = {"nodes": reduced_nodes, "edges": reduced_edges, "metadata": metadata}
        os.makedirs(self.exp_dir, exist_ok=True)
        path = os.path.join(self.exp_dir, f"reduced_physical_{self.exp_id}.json")
        with open(path, "w") as f:
            f.write("{\n")
            f.write(f'  "nodes":{json.dumps(reduced_json["nodes"], separators=(",", ":"))},\n')
            f.write(f'  "edges":{json.dumps(reduced_json["edges"], separators=(",", ":"))},\n')
            f.write(f'  "metadata":{json.dumps(reduced_json["metadata"], separators=(",", ":"))}\n')
            f.write("}\n")
        print(f"[INFO] Saved reduced physical graph JSON to {path}")

    # -------------------------
    # Variabili SAT
    # -------------------------
    def x(self, i, a):
        return self.var_map[(i, a)]

    def add_clause(self, lits, ctype="generic"):
        key = tuple(sorted(lits))
        if not hasattr(self, 'clause_set'):
            self.clause_set = set()
        if key not in self.clause_set:
            self.clauses.append(list(lits))
            self.clause_type.append(ctype)
            self.clause_set.add(key)

    # -------------------------
    # Clausole CNF
    # -------------------------
    def encode_exactly_one_per_logical(self):
        for i in self.logical_nodes:
            lits = [self.x(i, a) for a in self.physical_nodes]
            if lits:
                self.add_clause(lits, "at_least_one")
            for a, b in combinations(self.physical_nodes, 2):
                self.add_clause([-self.x(i, a), -self.x(i, b)], "at_most_one")

    def encode_mutual_exclusion_on_physical(self):
        if self.allow_shared_physical:
            return
        for a in self.physical_nodes:
            for i, j in combinations(self.logical_nodes, 2):
                self.add_clause([-self.x(i, a), -self.x(j, a)], "mutual_exclusion")

    def encode_edge_consistency(self):
        phys_edges = set(tuple(sorted(e)) for e in self.G_phys.edges())
        for i, j in self.G_log.edges():
            for a in self.physical_nodes:
                for b in self.physical_nodes:
                    if a == b or (min(a, b), max(a, b)) not in phys_edges:
                        self.add_clause([-self.x(i, a), -self.x(j, b)], "edge_consistency")

    # -------------------------
    # Generazione CNF
    # -------------------------
    def generate(self):
        if not self.embeddable:
            print("[INFO] Skip CNF generation: problem not embeddable")
            for r in self.reject_reasons:
                print(f"  - {r}")
            return 0, 0
        self.encode_exactly_one_per_logical()
        self.encode_mutual_exclusion_on_physical()
        self.encode_edge_consistency()
        
    # -------------------------
    # Aggiungi clausola per centro logico → centro fisico
    # -------------------------
        if self.logical_center is not None and self.center_node is not None:
            self.add_clause([self.x(self.logical_center, self.center_node)], "center_mapping")
   
            
        return self.num_vars, len(self.clauses)

    # -------------------------
    # Scrittura DIMACS
    # -------------------------
    def write_dimacs(self, path):
        if not self.embeddable:
            print("[INFO] Skip writing DIMACS: problem not embeddable")
            return
        with open(path, 'w') as f:
            f.write(f"p cnf {self.num_vars} {len(self.clauses)}\n")
            for idx, (c, ctype) in enumerate(zip(self.clauses, self.clause_type), start=1):
                f.write(f"c id {idx} type {ctype}\n")
                f.write(' '.join(str(l) for l in c) + ' 0\n')
        print(f"Wrote DIMACS CNF with {self.num_vars} vars e {len(self.clauses)} clauses to {path}")
