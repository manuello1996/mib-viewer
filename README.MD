# Web MIB Browser (Single-File, No Compile)

A lightweight, single-file web application to **browse, search, and inspect SNMP MIB files**.  
Built with **Flask** (Python) and a custom best-effort **SMIv2 parser**, this tool does **not require PySMI or MIB compilation**. Just upload your `.mib` or `.txt` files and start exploring the OID tree in your browser.  

![screenshot](/screenshot/app.png/)
![screenshot](/screenshot/inspector.png)

---

## ✨ Features

- **Self-contained**: a single Python file (`mib_browser.py`)  
- **No compilation**: parses textual MIB definitions directly  
- **Tree viewer**: browsable, expandable/collapsible OID hierarchy  
- **Inspector panel**: pinned sidebar showing details of selected nodes  
- **Full-text search**: search by name, OID, type, or description  
- **Dark mode**
- **Copy helpers**: quickly copy OIDs or names  

---

## 🚀 Getting Started

### Requirements
- Python **3.8+**
- [Flask](https://flask.palletsprojects.com/)  

Install dependencies:

```bash
pip install flask
```

### Run the app

```bash
python mib_browser.py
```

By default the app runs on [http://localhost:8000](http://localhost:8000).

---

## 📂 Usage

1. Open the web UI in your browser.  
2. Upload one or more `.mib` / `.txt` files (raw SMIv2 text).  
3. Select a module from the left panel.  
4. Explore the **tree view** of OIDs.  
   - Expand/collapse nodes  
   - Inspect details in the right-side **Inspector panel**  
   - Copy OIDs or names with one click  
5. Use the **search bar** to locate nodes across all modules.  

---

## 🔎 Inspector Panel

- **Pinned by default** (sticks as you scroll)  
- Displays: Name, OID, Class, Syntax, Description, and Breadcrumb path  
- Actions: Copy OID / Copy Name / Expand levels / callapse tree

---

## 🛠 Development Notes

- Uses a **custom regex parser** for SMIv2; not 100% spec-compliant but works for most vendor MIBs.  
- Uploaded files are stored in a temporary directory (`/tmp/web_mib_uploads`) for the session. 
- MIB files, or folder containig MIB files, are automatically loaded in the app at start. 
- No database, no extra services—just Flask + static HTML/JS.  
