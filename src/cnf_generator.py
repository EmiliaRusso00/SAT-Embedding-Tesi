from itertools import combinations
import networkx as nx
import json
import os


class CNFGenerator:

    def __init__(self, G_log, G_phys, G_log_json=None, G_phys_json=None,
                 exp_dir=None, exp_id=0, skip_reduction=False,
                 physical_center=None, stream_path=None):
        """
        G_log: grafo logico (NetworkX)
        G_phys: grafo fisico (NetworkX)
        physical_center: nodo centrale fisico da usare per riduzione
        stream_path: se fornito, scrive clausole DIMACS direttamente su file
        """
        self.G_log = G_log
        self.G_phys_original = G_phys
        self.G_log_json = G_log_json
        self.G_phys_json = G_phys_json
        self.exp_dir = exp_dir
        self.exp_id = exp_id
        self.skip_reduction = skip_reduction
        self.forced_physical_center = physical_center
        self.stream_path = stream_path

        self.embeddable = True
        self.reject_reasons = []

        # -------------------------
        # Riduzione o full graph
        # -------------------------
        if self.skip_reduction:
            print("[INFO] Variante FULL: nessuna riduzione del grafo fisico.")
            self.G_phys = self.G_phys_original.copy()
            self.center_node = None
            self.logical_center = None
            self.phys_radius = None
        else:
            if self.forced_physical_center is None:
                raise RuntimeError("Per la variante ridotta serve un centro fisico specificato")
            print("[INFO] Variante REDUCED: estrazione sottografo fisico centrato.")
            self.G_phys, self.center_node, self.logical_center, self.phys_radius = \
                self._extract_physical_subgraph(self.G_phys_original, self.G_log, self.forced_physical_center)

        # -------------------------
        # Precheck embedding
        # -------------------------
        try:
            self._precheck_embedding(self.G_log, self.G_phys)
        except Exception as e:
            self.embeddable = False
            self.reject_reasons.append(f"Errore durante precheck: {e}")
            print(f"[WARN] Errore durante precheck embedding: {e}")

        # -------------------------
        # Salvataggio JSON ridotto se necessario
        # -------------------------
        if self.G_phys is not None and len(self.G_phys.nodes()) and self.exp_dir:
            try:
                self._save_reduced_phys_json()
            except Exception as e:
                print(f"[WARN] Non sono riuscito a salvare reduced JSON: {e}")

        # -------------------------
        # Ordinamento nodi e mappa variabili SAT
        # -------------------------
        self.logical_nodes = list(sorted(G_log.nodes()))
        self.physical_nodes = list(sorted(self.G_phys.nodes()))
        self.n = len(self.logical_nodes)
        self.m = len(self.physical_nodes)
        self.var_map = {}
        vid = 1
        for i in self.logical_nodes:
            for a in self.physical_nodes:
                self.var_map[(i, a)] = vid
                vid += 1
        self.num_vars = vid - 1

        # -------------------------
        # Apertura file streaming
        # -------------------------
        if self.stream_path:
            os.makedirs(os.path.dirname(self.stream_path), exist_ok=True)
            self.f_stream = open(self.stream_path, "w")
            self.num_clauses_written = 0
            # placeholder p cnf, sarà aggiornato a fine scrittura
            self.f_stream.write(f"p cnf {self.num_vars} 0\n")
        else:
            self.f_stream = None
            self.clause_set = set()    # solo se non in streaming
            self.clauses = []
            self.clause_type = []

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

        if nx.is_connected(G_log):
            comp_sizes = [len(c) for c in nx.connected_components(G_phys)]
            max_comp = max(comp_sizes) if comp_sizes else 0
            if max_comp < n_log:
                self.embeddable = False
                self.reject_reasons.append(f"Componente fisica più grande < |V_log|={n_log}")
                print(f"[PRUNE] {self.reject_reasons[-1]}")
                return

        self.embeddable = True

    # -------------------------
    def _extract_physical_subgraph(self, G_phys, G_log, forced_center):
        components = list(nx.connected_components(G_phys))
        comp = max(components, key=len)
        G_comp = G_phys.subgraph(comp).copy()

        logical_center = nx.center(G_log)[0]
        min_degree_required = G_log.degree(logical_center)
        print(f"[INFO] Centro logico: {logical_center} (grado {min_degree_required})")

        if G_comp.degree(forced_center) < min_degree_required:
            raise RuntimeError(f"Centro fisico {forced_center} non soddisfa grado minimo richiesto {min_degree_required}")

        physical_center = forced_center
        distances_phys = nx.single_source_shortest_path_length(G_comp, physical_center)
        distances_log = nx.single_source_shortest_path_length(G_log, logical_center)
        max_dist_log = max(distances_log.values())

        chosen_nodes = [n for n, d in distances_phys.items() if d <= max_dist_log]
        G_sub = G_comp.subgraph(chosen_nodes).copy()
        print(f"[INFO] Sottografo ridotto: {len(G_sub)} nodi selezionati intorno al centro fisico {physical_center}")

        return G_sub, physical_center, logical_center, max_dist_log

    # -------------------------
    def _save_reduced_phys_json(self):
        metadata = {}
        if isinstance(self.G_phys_json, dict):
            metadata = self.G_phys_json.get("metadata", {})
        metadata.update({
            "physical_center": self.center_node,
            "physical_center_degree": self.G_phys.degree(self.center_node) if self.center_node else None,
            "logical_center": self.logical_center,
            "logical_center_degree": self.G_log.degree(self.logical_center) if self.logical_center else None,
            "num_logical_nodes": len(self.G_log),
            "num_physical_nodes": len(self.G_phys)
        })
        reduced_json = {
            "nodes": list(self.G_phys.nodes()),
            "edges": [list(e) for e in self.G_phys.edges()],
            "metadata": metadata
        }
        os.makedirs(self.exp_dir, exist_ok=True)
        path = os.path.join(self.exp_dir, f"reduced_physical_{self.exp_id}.json")
        with open(path, "w") as f:
            json.dump(reduced_json, f, separators=(",", ":"))
        print(f"[INFO] Saved reduced physical graph JSON to {path}")

    # -------------------------
    def x(self, i, a):
        return self.var_map[(i, a)]

    def add_clause(self, lits, ctype="generic"):
        if self.f_stream:
            self.f_stream.write(f"c type {ctype}\n")
            self.f_stream.write(' '.join(str(l) for l in lits) + " 0\n")
            self.num_clauses_written += 1
        else:
            key = tuple(sorted(lits))
            if key in self.clause_set:
                return
            self.clause_set.add(key)
            self.clauses.append(list(lits))
            self.clause_type.append(ctype)

    # -------------------------
    def encode_exactly_one_per_logical(self):
        for i in self.logical_nodes:
            lits = [self.x(i, a) for a in self.physical_nodes]
            if lits:
                self.add_clause(lits, "at_least_one")
            for a, b in combinations(self.physical_nodes, 2):
                self.add_clause([-self.x(i, a), -self.x(i, b)], "at_most_one")

    def encode_mutual_exclusion_on_physical(self):
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
    def generate(self):
        if not self.embeddable:
            print("[INFO] Skip CNF generation: problem not embeddable")
            return 0, 0

        self.encode_exactly_one_per_logical()
        self.encode_mutual_exclusion_on_physical()
        self.encode_edge_consistency()

        if self.logical_center is not None and self.center_node is not None:
            self.add_clause([self.x(self.logical_center, self.center_node)], "center_mapping")

        if self.exp_dir:
            unsat_path = os.path.join(self.exp_dir, "unsat_analysis.txt")
            if os.path.exists(unsat_path):
                with open(unsat_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and line.endswith(")") and " 0" in line:
                            tokens = line.split()
                            try:
                                var_id = int(tokens[0])
                                self.add_clause([var_id], "forced_unsat")
                            except Exception:
                                pass

        if self.f_stream:
            # Aggiorna header p cnf
            self.f_stream.seek(0)
            self.f_stream.write(f"p cnf {self.num_vars} {self.num_clauses_written}\n")
            self.f_stream.close()
            return self.num_vars, self.num_clauses_written
        else:
            return self.num_vars, len(self.clauses)

    # -------------------------
    def write_dimacs(self, path):
        if not self.embeddable:
            print("[INFO] Skip writing DIMACS: problem not embeddable")
            return

        if self.f_stream:
            print(f"[INFO] DIMACS già scritto in streaming: {self.stream_path}")
            return

        with open(path, 'w') as f:
            f.write(f"p cnf {self.num_vars} {len(self.clauses)}\n")
            for idx, (c, ctype) in enumerate(zip(self.clauses, self.clause_type), start=1):
                f.write(f"c id {idx} type {ctype}\n")
                f.write(' '.join(str(l) for l in c) + ' 0\n')
        print(f"[INFO] Wrote DIMACS CNF with {self.num_vars} vars e {len(self.clauses)} clauses to {path}")
