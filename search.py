from typing import Dict, Any, List

def flatten_nodes(module: str, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recursively flatten a tree of nodes into a list."""
    flat_list = []
    for node in nodes:
        # Create a copy to avoid modifying the original node data
        node_copy = node.copy()
        children = node_copy.pop('children', [])
        flat_list.append(node_copy)
        if children:
            flat_list.extend(flatten_nodes(module, children))
    return flat_list

def search_all(term: str, compiled_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Performs a full-text search across all compiled MIBs."""
    term = (term or "").strip().lower()
    if not term:
        return []

    hits: List[Dict[str, Any]] = []
    
    # Pre-flatten all nodes if not already done
    # For performance, this could be cached.
    all_nodes = []
    for mod, entry in compiled_data.items():
        all_nodes.extend(flatten_nodes(mod, entry.get("doc", [])))
        
    for n in all_nodes:
        haystack = " ".join([
            str(n.get(key, "")) for key in ["module", "name", "oid", "sym_oid", "klass", "syntax", "description"]
        ]).lower()

        if term in haystack:
            hits.append({
                "name": n.get("name"),
                "module": n.get("module"),
                "oid": n.get("oid"),
                "description": (n.get("description") or "")[:100] # Truncate for preview
            })
        
        if len(hits) >= 200:
            break
            
    return hits
