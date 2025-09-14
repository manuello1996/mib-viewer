# parser.py (Rewritten for Robustness)

import re
from typing import Dict, Any, List, Tuple, Optional
class SmiV2Parser:
    def __init__(self, text: str):
        text_no_comments = re.sub(r'--.*', '', text)
        self.raw = text_no_comments.replace('-\n', '').replace('\r', '')
        self.module_name: Optional[str] = None
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.imports: Dict[str, List[str]] = {}
        self.module_identity: Dict[str, Any] = {}

    def parse(self) -> Tuple[Optional[str], Dict[str, Any]]:
        self.module_name = self._get_module_name()
        if not self.module_name:
            return None, {}
        
        self._get_imports()
        
        self._pass1_discover_nodes()
        self._pass2_resolve_oids()
        doc = self._pass3_build_tree()
        
        return self.module_name, {
            "doc": doc,
            "imports": self.imports,
            "module_identity": self.module_identity,
            "nodes_map": self.nodes
        }

    def _get_module_name(self) -> Optional[str]:
        m = re.search(r'([a-zA-Z0-9-]+)\s+DEFINITIONS\s*::=\s*BEGIN', self.raw, re.DOTALL)
        return m.group(1) if m else None

    def _get_imports(self):
        m = re.search(r'IMPORTS\s+(.*?);', self.raw, re.DOTALL)
        if m:
            clauses = re.findall(r'([\w\d\s,-]+?)\s+FROM\s+([a-zA-Z0-9-]+)', m.group(1))
            for items_str, from_module in clauses:
                items = [item.strip() for item in items_str.replace('\n', ' ').split(',') if item.strip()]
                self.imports[from_module] = items

    def _pass1_discover_nodes(self):
        pattern = re.compile(
            r'([a-zA-Z0-9-]+)\s+'
            r'(OBJECT-TYPE|OBJECT IDENTIFIER|MODULE-IDENTITY|OBJECT-GROUP|NOTIFICATION-TYPE|TRAP-TYPE|TEXTUAL-CONVENTION)\s+'
            r'(.*?)'
            r'::=\s*\{(.*?)\}',
            re.DOTALL
        )
        for m in pattern.finditer(self.raw):
            name, klass, body, oid_def = m.groups()
            if name == 'MACRO': continue
            
            self.nodes[name] = {
                'name': name,
                'klass': klass.replace(' ', '-'),
                'oid_def': oid_def.strip(),
                'description': self._get_description(body),
                'syntax': self._get_syntax(body),
                'module': self.module_name,
                'children': []
            }
            if self.nodes[name]['klass'] == 'MODULE-IDENTITY':
                self.module_identity = self.nodes[name]

    def _pass2_resolve_oids(self):
        oid_map = {'iso': '1'}
        resolved_in_pass = True
        while resolved_in_pass:
            resolved_in_pass = False
            for name, node in self.nodes.items():
                if 'oid' in node: continue

                parent_name, sub_id = self._parse_oid_def(node['oid_def'])
                if not parent_name: continue

                parent_oid = oid_map.get(parent_name)
                if not parent_oid:
                    parent_node = self.nodes.get(parent_name)
                    if parent_node and 'oid' in parent_node:
                        parent_oid = parent_node['oid']
                
                if parent_oid and sub_id.isdigit():
                    node['oid'] = f"{parent_oid}.{sub_id}"
                    node['sym_oid'] = f"{{{parent_name} {sub_id}}}"
                    oid_map[name] = node['oid']
                    resolved_in_pass = True

    def _pass3_build_tree(self) -> list:
        nodes_by_oid = {node['oid']: node for node in self.nodes.values() if 'oid' in node}
        root_nodes = []
        sorted_oids = sorted(nodes_by_oid.keys(), key=lambda x: [int(i) for i in x.split('.')])

        for oid in sorted_oids:
            node = nodes_by_oid[oid]
            oid_parts = oid.split('.')
            if len(oid_parts) > 1:
                parent_oid = ".".join(oid_parts[:-1])
                parent_node = nodes_by_oid.get(parent_oid)
                if parent_node:
                    parent_node['children'].append(node)
                    continue
            root_nodes.append(node)
            
        return root_nodes

    def _parse_oid_def(self, oid_def: str) -> Tuple[Optional[str], Optional[str]]:
        parts = oid_def.split()
        if len(parts) == 2:
            return parts[0], parts[1]
        elif len(parts) == 1 and parts[0].isdigit():
             return 'iso', parts[0]
        return None, None

    # --- RESTORED HELPER METHODS ---
    def _get_description(self, text: str) -> Optional[str]:
        m = re.search(r'DESCRIPTION\s+"(.*?)"', text, re.DOTALL)
        return m.group(1).strip().replace('\n', ' ') if m else None

    def _get_syntax(self, text: str) -> Optional[str]:
        m = re.search(r'SYNTAX\s+(.*?)(MAX-ACCESS|ACCESS|STATUS|DESCRIPTION|INDEX|::=)', text, re.DOTALL)
        return m.group(1).strip().replace('\n', ' ') if m else None