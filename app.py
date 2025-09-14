# app.py (Reverted)

import os
import html
from pathlib import Path
from flask import Flask, request, jsonify, render_template, redirect, url_for
from werkzeug.utils import secure_filename

# Revert to the original SmiV2Parser
from parser import SmiV2Parser
from search import search_all

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Global Data Store ---
COMPILED = {}

# --- [RESTORED] Original MIB Loading Logic ---
def load_mibs_from_disk():
    print("Loading MIBs from 'MIB' directory...")
    mib_root = Path("MIB")
    if not mib_root.is_dir():
        print("Warning: 'MIB' directory not found. No local MIBs will be loaded.")
        return
        
    mib_paths = list(mib_root.rglob("*.mib")) + list(mib_root.rglob("*.txt"))
    for path in mib_paths:
        try:
            content = path.read_text(errors='ignore')
            add_mib_content(content, source=str(path))
        except Exception as e:
            print(f"Error processing {path}: {e}")

def add_mib_content(content: str, source: str):
    """Parses MIB content using the original SmiV2Parser."""
    try:
        parser = SmiV2Parser(content)
        module_name, parsed_data = parser.parse()
        
        if not module_name:
            print(f"  [Parse Failure] Could not extract a valid module name from '{source}'. Skipping.")
            return

        if parsed_data and parsed_data.get("doc"):
            parsed_data['source'] = source
            COMPILED[module_name] = parsed_data
            print(f"  Successfully loaded module '{module_name}' from {source}")
        else:
            print(f"  [Parse Warning] Found module '{module_name}' in '{source}' but no data was parsed. Skipping.")

    except Exception as e:
        import traceback
        print(f"  [Exception] An error occurred while parsing '{source}': {e}")
        traceback.print_exc()

def build_modlist_html() -> str:
    """Builds the HTML for the sidebar module list, showing the filename."""
    paths = {}
    for mod, data in COMPILED.items():
        source_path = Path(data.get('source', 'Uploaded'))
        folder = str(source_path.parent)
        filename = source_path.name
        
        if folder not in paths:
            paths[folder] = []
        
        paths[folder].append((mod, filename))

    html_out = ""
    for folder, mods_with_filenames in sorted(paths.items()):
        folder_disp = folder.replace('\\', '/') if folder != '.' else 'Local MIBs'
        html_out += f"<details open><summary>{html.escape(folder_disp)}</summary><ul>"
        for mod, filename in sorted(mods_with_filenames, key=lambda x: x[1]):
            html_out += f'<li><a href="#" data-module="{mod}">{html.escape(filename)}</a></li>'
        html_out += "</ul></details>"
        
    return html_out

# --- Routes (Keep all the UI-related routes) ---
@app.route("/")
def index():
    return render_template(
        "index.html",
        modules=sorted(COMPILED.keys()),
        modlist_html=build_modlist_html()
    )

@app.route("/module/<mod_name>")
def get_module(mod_name):
    if mod_name not in COMPILED:
        return jsonify({"error": "Module not found"}), 404
    oid = request.args.get('oid')
    if oid:
        nodes_map = COMPILED[mod_name].get("nodes_map", {})
        node_data = next((node for node in nodes_map.values() if node.get('oid') == oid), None)
        if node_data:
            return jsonify(node_data)
        else:
            return jsonify({"error": "OID not found in module"}), 404
    else:
        return jsonify(COMPILED[mod_name])

@app.route("/search")
def search():
    term = request.args.get("term", "")
    hits = search_all(term, COMPILED)
    return jsonify(hits)

@app.route("/upload", methods=["POST"])
def upload():
    if 'file[]' not in request.files:
        return redirect(url_for('index'))
    
    files = request.files.getlist('file[]')
    for file in files:
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            content = file.read().decode('utf-8', errors='ignore')
            add_mib_content(content, source=f"Uploads/{filename}")

    return redirect(url_for('index'))


@app.route("/clear", methods=["POST"])
def clear_all():
    global COMPILED
    COMPILED = {}
    print("Cleared all loaded data.")
    return redirect(url_for("index"))

# --- Main Execution ---
if __name__ == "__main__":
    load_mibs_from_disk()
    print(f"Ready. Loaded {len(COMPILED)} modules.")
    app.run(host="0.0.0.0", port=5000, debug=True)
