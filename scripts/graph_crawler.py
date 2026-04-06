import os
import re
import json
from collections import defaultdict

# Move to app root to ensure paths are evaluated globally relative to the project
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(app_root)

# Target entry directories configured by user
SVELTE_DIRS = ["src/routes", "src/lib"]
RUST_DIRS = ["src-tauri/src", "Canvas/canvas-engine/src"]
PYTHON_DIR = "src-tauri/src-python/sushi"
PYTHON_ROUTER = os.path.normpath("src-tauri/src-python/sushi/commands.py")

# Graph datasets
nodes = {}
links = []

# Unified project registry: norm_path -> group
project_files = {}

# Maps for IPC mapping
tauri_commands = {}  # command name -> Rust file path
python_commands = {}  # command name -> Python file path
svelte_calls_rust = defaultdict(list)  # Svelte file -> [commands]

# File signatures for multifaceted matching: fpath -> { 'symbols': set(), 'patterns': set(), 'group': str }
file_metadata = defaultdict(lambda: {"symbols": set(), "patterns": set(), "group": ""})
file_contents_cache = {}

# Regexes for signature extraction
REGEX_PY_CLASS = re.compile(r"^class\s+([a-zA-Z0-9_]+)", re.MULTILINE)
REGEX_PY_FUNC = re.compile(r"^def\s+([a-zA-Z0-9_]+)\s*\(", re.MULTILINE)
REGEX_RS_STRUCT = re.compile(r"^(?:pub\s+)?struct\s+([a-zA-Z0-9_]+)", re.MULTILINE)
REGEX_RS_ENUM = re.compile(r"^(?:pub\s+)?enum\s+([a-zA-Z0-9_]+)", re.MULTILINE)
REGEX_RS_FUNC = re.compile(r"^(?:pub\s+)?fn\s+([a-zA-Z0-9_]+)\s*\(", re.MULTILINE)
REGEX_SVELTE_EXPORT = re.compile(
    r"export\s+(?:const|let|var|function|class)\s+([a-zA-Z0-9_]+)", re.MULTILINE
)
# Matches invoke('cmd') or pyInvoke('cmd')
REGEX_IPC_CALL = re.compile(
    r"(?:invoke|pyInvoke|canvasInvoke|canvasCommand)\s*\(\s*['\"]([^'\"#]+)['\"]"
)


def add_node(file_path, group):
    norm = os.path.normpath(file_path)
    if norm not in nodes:
        nodes[norm] = {"id": norm, "label": os.path.basename(norm), "group": group}
    return norm


def add_edge(source, target, edge_type="internal"):
    if target not in nodes:
        nodes[target] = {
            "id": target,
            "label": os.path.basename(target),
            "group": "external",
        }

    # Avoid duplicate edges
    for link_obj in links:
        if (
            link_obj["source"] == source
            and link_obj["target"] == target
            and link_obj["type"] == edge_type
        ):
            return

    links.append({"source": source, "target": target, "type": edge_type})


def strip_comments(text, ext):
    if ext in (".svelte", ".ts", ".js"):
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"//.*", "", text)
    elif ext == ".py":
        text = re.sub(r"#.*", "", text)
    elif ext == ".rs":
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"//.*", "", text)
    return text


def extract_signatures(fpath, content, group):
    meta = file_metadata[fpath]
    meta["group"] = group
    stem = os.path.splitext(os.path.basename(fpath))[0]

    if stem not in {"mod", "lib", "main", "index", "__init__"}:
        meta["patterns"].add(stem)

    if group == "python":
        for m in REGEX_PY_CLASS.findall(content):
            meta["symbols"].add(m)
        for m in REGEX_PY_FUNC.findall(content):
            if not m.startswith("_"):
                meta["symbols"].add(m)
        if "src-python" in fpath:
            rel = os.path.relpath(fpath, "src-tauri/src-python")
            mod_path = os.path.splitext(rel)[0].replace(os.sep, ".")
            meta["patterns"].add(mod_path)
    elif group == "rust":
        for m in REGEX_RS_STRUCT.findall(content):
            meta["symbols"].add(m)
        for m in REGEX_RS_ENUM.findall(content):
            meta["symbols"].add(m)
        for m in REGEX_RS_FUNC.findall(content):
            meta["symbols"].add(m)
    elif group == "svelte":
        for m in REGEX_SVELTE_EXPORT.findall(content):
            meta["symbols"].add(m)
        if fpath.endswith(".svelte"):
            meta["patterns"].add(f"<{stem}")


def build_project_registry():
    print("Building project registry...")
    for d in SVELTE_DIRS:
        if not os.path.exists(d): continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".svelte", ".ts", ".js")):
                    project_files[os.path.normpath(os.path.join(root, f))] = "svelte"
    for d in RUST_DIRS:
        if not os.path.exists(d): continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".rs"):
                    project_files[os.path.normpath(os.path.join(root, f))] = "rust"
    if os.path.exists(PYTHON_DIR):
        for root, _, files in os.walk(PYTHON_DIR):
            for f in files:
                if f.endswith(".py"):
                    project_files[os.path.normpath(os.path.join(root, f))] = "python"
    for path, group in project_files.items():
        add_node(path, group)
    print(f"Registry built with {len(project_files)} internal files.")


def resolve_svelte_import(current_file, imp):
    if imp.startswith("$lib"):
        res = imp.replace("$lib", "src/lib")
        for ext in (".ts", ".svelte", ".js"):
            if os.path.exists(res + ext): return os.path.normpath(res + ext)
            if os.path.exists(os.path.join(res, "index" + ext)): return os.path.normpath(os.path.join(res, "index" + ext))
        return os.path.normpath(res)
    elif imp.startswith("."):
        dir_name = os.path.dirname(current_file)
        res = os.path.join(dir_name, imp)
        for ext in (".ts", ".svelte", ".js"):
            if os.path.exists(res + ext): return os.path.normpath(res + ext)
            if os.path.exists(os.path.join(res, "index" + ext)): return os.path.normpath(os.path.join(res, "index" + ext))
        return os.path.normpath(res)
    return imp


def scan_svelte():
    import_re = re.compile(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]|import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
    for fpath, group in project_files.items():
        if group != "svelte": continue
        with open(fpath, "r", encoding="utf-8") as f:
            raw_content = f.read()
            content = strip_comments(raw_content, os.path.splitext(fpath)[1])
            extract_signatures(fpath, content, "svelte")
            for m in import_re.findall(content):
                imp = next(s for s in m if s)
                res = resolve_svelte_import(fpath, imp)
                if "canvas-engine" in res and "pkg" in res:
                    add_edge(fpath, os.path.normpath("Canvas/canvas-engine/src/lib.rs"), "ipc")
                elif imp.startswith(".") or imp.startswith("$lib"):
                    add_edge(fpath, res, "internal")
                else:
                    add_edge(fpath, imp, "external")


def resolve_rust_import(current_file, mod_name):
    dir_name = os.path.dirname(current_file)
    p1 = os.path.normpath(os.path.join(dir_name, mod_name + ".rs"))
    p2 = os.path.normpath(os.path.join(dir_name, mod_name, "mod.rs"))
    if p1 in project_files: return p1
    if p2 in project_files: return p2
    return mod_name


def scan_rust():
    mod_re = re.compile(r"^\s*(?:pub\s+)?mod\s+([a-zA-Z0-9_]+);", re.MULTILINE)
    use_re = re.compile(r"^\s*(?:pub\s+)?use\s+([a-zA-Z0-9_:]+)", re.MULTILINE)
    tauri_cmd_re = re.compile(r"#\[tauri::command\][\s\S]*?fn\s+([a-zA-Z0-9_]+)\s*\(")
    for fpath, group in project_files.items():
        if group != "rust": continue
        with open(fpath, "r", encoding="utf-8") as f:
            raw_content = f.read()
            content = strip_comments(raw_content, ".rs")
            extract_signatures(fpath, content, "rust")
            for m in mod_re.findall(content):
                add_edge(fpath, resolve_rust_import(fpath, m), "internal")
            for u in use_re.findall(content):
                parts = u.split("::")
                if parts[0] == "sushi_lib": add_edge(fpath, os.path.normpath("src-tauri/src/lib.rs"), "internal")
                elif parts[0] == "tauri": add_edge(fpath, "tauri", "external")
            for cmd in tauri_cmd_re.findall(content):
                tauri_commands[cmd] = fpath


def scan_python():
    import_re1 = re.compile(r"^\s*import\s+([a-zA-Z0-9_.]+)", re.MULTILINE)
    import_re2 = re.compile(r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import", re.MULTILINE)
    py_cmd_re = re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(", re.MULTILINE)
    for fpath, group in project_files.items():
        if group != "python": continue
        with open(fpath, "r", encoding="utf-8") as f:
            raw_content = f.read()
            content = strip_comments(raw_content, ".py")
            extract_signatures(fpath, content, "python")
            for imp in import_re1.findall(content) + import_re2.findall(content):
                if imp.startswith("sushi"):
                    rel = imp.replace(".", os.sep)
                    target = os.path.normpath(os.path.join("src-tauri/src-python", rel + ".py"))
                    if target not in project_files:
                        target = os.path.normpath(os.path.join("src-tauri/src-python", rel, "__init__.py"))
                    if target in project_files: add_edge(fpath, target, "internal")
                else: add_edge(fpath, imp, "external")
            if os.path.basename(fpath) == "commands.py":
                for cmd in py_cmd_re.findall(content):
                    python_commands[cmd] = fpath


def perform_global_search():
    print("Performing global mention search (Pass 2)...")
    structural_count = 0
    mention_count = 0
    for fpath in project_files:
        with open(fpath, "r", encoding="utf-8") as f:
            ext = os.path.splitext(fpath)[1]
            file_contents_cache[fpath] = strip_comments(f.read(), ext if ext else ".py")
    for target_path, meta in file_metadata.items():
        symbols = meta["symbols"]
        patterns = meta["patterns"]
        target_stem = os.path.splitext(os.path.basename(target_path))[0]
        for source_path, content in file_contents_cache.items():
            if source_path == target_path: continue
            found_symbol = None
            for sym in symbols:
                if len(sym) < 4: continue
                if re.search(rf"\b{re.escape(sym)}\b", content):
                    found_symbol = sym
                    break
            if found_symbol:
                add_edge(source_path, target_path, "structural")
                structural_count += 1
                continue
            found_pattern = False
            for pat in patterns:
                if re.search(rf"\b{re.escape(pat)}\b", content):
                    found_pattern = True
                    break
            if found_pattern:
                add_edge(source_path, target_path, "mention")
                mention_count += 1
                continue
            if target_stem not in {"mod", "lib", "main", "index", "__init__"}:
                if re.search(rf"\b{re.escape(target_stem)}\s*[\.\(]", content):
                    add_edge(source_path, target_path, "mention")
                    mention_count += 1
    print(f"Pass 2 completed. Discovered {structural_count} structural links and {mention_count} mentions.")


def build_ipc_edges():
    print("Building IPC bridges...")
    symbol_to_file = {}
    for fpath, meta in file_metadata.items():
        for sym in meta["symbols"]:
            if os.path.basename(fpath) == "commands.py" or meta.get("group") == "rust":
                symbol_to_file[sym] = fpath
    for source_path, content in file_contents_cache.items():
        for cmd in REGEX_IPC_CALL.findall(content):
            if cmd in symbol_to_file: add_edge(source_path, symbol_to_file[cmd], "ipc")
            elif cmd in python_commands: add_edge(source_path, python_commands[cmd], "ipc")
            elif cmd in tauri_commands: add_edge(source_path, tauri_commands[cmd], "ipc")
            else:
                unresolved = f"ipc_cmd:{cmd}"
                add_node(unresolved, "unresolved_ipc")
                add_edge(source_path, unresolved, "ipc")
    lib_rs = os.path.normpath("src-tauri/src/lib.rs")
    engine_rs = os.path.normpath("Canvas/canvas-engine/src/lib.rs")
    if lib_rs in project_files and engine_rs in project_files: add_edge(lib_rs, engine_rs, "internal")


def generate_html():
    graph_data = {"nodes": list(nodes.values()), "links": links}
    template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sushi Enhanced Dependency Graph</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body { margin: 0; padding: 0; overflow: hidden; background: #0f172a; font-family: 'Inter', sans-serif; color: #e2e8f0; }
        #ui-overlay { position: absolute; top: 0; left: 0; right: 0; pointer-events: none; padding: 20px; display: flex; justify-content: space-between; }
        #info-panel { pointer-events: auto; background: rgba(30, 41, 59, 0.9); padding: 20px; border-radius: 12px; border: 1px solid #334155; width: 300px; backdrop-filter: blur(8px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); }
        .header { font-weight: 700; font-size: 16px; color: #f8fafc; margin-bottom: 8px; }
        .path { font-size: 11px; color: #94a3b8; word-break: break-all; margin-bottom: 12px; font-family: 'JetBrains Mono', monospace; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 10px; font-weight: 600; text-transform: uppercase; }
        .legend { pointer-events: auto; background: rgba(30, 41, 59, 0.9); padding: 15px; border-radius: 12px; border: 1px solid #334155; font-size: 11px; font-weight: 500; backdrop-filter: blur(8px); }
        .legend-title { font-size: 13px; font-weight: 700; margin-bottom: 10px; color: #94a3b8; }
        .legend-item { display: flex; align-items: center; margin-bottom: 6px; }
        .legend-color { width: 10px; height: 10px; border-radius: 50%; margin-right: 10px; }
        .legend-line { height: 2px; width: 20px; margin-right: 10px; }
        .badge-svelte { background-color: #ef4444; color: white; }
        .badge-rust { background-color: #f59e0b; color: #000; }
        .badge-python { background-color: #3b82f6; color: white; }
        .badge-external { background-color: #64748b; color: white; }
        .badge-unresolved_ipc { background-color: #e11d48; color: white; }
    </style>
</head>
<body>
    <div id="ui-overlay">
        <div id="info-panel">
            <div class="header">Sushi Architecture</div>
            <div class="path">Hover a node to inspect...</div>
        </div>
        <div class="legend">
            <div class="legend-title">Components</div>
            <div class="legend-item"><div class="legend-color" style="background:#ef4444"></div> Svelte Frontend</div>
            <div class="legend-item"><div class="legend-color" style="background:#f59e0b"></div> Rust Orchestrator</div>
            <div class="legend-item"><div class="legend-color" style="background:#3b82f6"></div> Python Services</div>
            <div class="legend-item"><div class="legend-color" style="background:#64748b"></div> External</div>
            <br>
            <div class="legend-title">Connections</div>
            <div class="legend-item"><div class="legend-line" style="background:#475569"></div> File Import</div>
            <div class="legend-item"><div class="legend-line" style="background:#22c55e"></div> Structural Link</div>
            <div class="legend-item"><div class="legend-line" style="background:#db2777"></div> IPC Bridge</div>
            <div class="legend-item"><div class="legend-line" style="background:#475569; border: 1px dashed #94a3b8; height: 0"></div> Global Mention</div>
        </div>
    </div>
    <div id="graph"></div>
    <script>
        const data = __GRAPH_DATA__;
        const width = window.innerWidth;
        const height = window.innerHeight;
        const colorMap = {
            "svelte": "#ef4444", "rust": "#f59e0b", "python": "#3b82f6",
            "external": "#64748b", "unresolved_ipc": "#e11d48"
        };
        const svg = d3.select("#graph").append("svg").attr("width", width).attr("height", height);
        svg.append("defs").selectAll("marker")
            .data(["internal", "ipc", "mention", "structural"])
            .join("marker")
            .attr("id", d => `arrow-${d}`)
            .attr("viewBox", "0 -5 10 10").attr("refX", 22).attr("refY", 0)
            .attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto")
            .append("path")
            .attr("fill", d => {
                if (d === "ipc") return "#db2777";
                if (d === "structural") return "#22c55e";
                if (d === "mention") return "#64748b";
                return "#475569";
            })
            .attr("d", "M0,-5L10,0L0,5");
        const g = svg.append("g");
        svg.call(d3.zoom().scaleExtent([0.05, 5]).on("zoom", (e) => g.attr("transform", e.transform)));
        const simulation = d3.forceSimulation(data.nodes)
            .force("link", d3.forceLink(data.links).id(d => d.id).distance(d => d.type === 'mention' ? 250 : 120))
            .force("charge", d3.forceManyBody().strength(-500))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(35));
        const link = g.append("g").selectAll("line").data(data.links).join("line")
            .attr("stroke", d => {
                if (d.type === 'ipc') return "#db2777";
                if (d.type === 'structural') return "#22c55e";
                return "#334155";
            })
            .attr("stroke-width", d => {
                if (d.type === 'ipc' || d.type === 'structural') return 2.5;
                if (d.type === 'mention') return 1;
                return 1.5;
            })
            .attr("stroke-dasharray", d => d.type === 'mention' ? "4,4" : "none")
            .attr("marker-end", d => `url(#arrow-${d.type})`)
            .attr("opacity", d => d.type === 'mention' ? 0.3 : 1);
        const node = g.append("g").selectAll("g").data(data.nodes).join("g")
            .call(d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended));
        node.append("circle").attr("r", 10)
            .attr("fill", d => colorMap[d.group] || "#334155")
            .attr("stroke", "#f8fafc").attr("stroke-width", 2)
            .on("mouseover", (e, d) => {
                d3.select("#info-panel").html(`<div class="header">${d.label}</div><div class="path">${d.id}</div><span class="badge badge-${d.group}">${d.group}</span>`);
            })
            .on("click", (e, d) => { e.stopPropagation(); highlightNode(d); });
        svg.on("click", () => resetHighlight());
        function highlightNode(d) {
            node.style("opacity", 0.15); link.style("opacity", 0.05);
            const neighbors = new Set(); neighbors.add(d.id);
            link.filter(l => l.source.id === d.id || l.target.id === d.id)
                .style("opacity", 1)
                .style("stroke-width", l => (l.type === 'ipc' || l.type === 'structural' ? 4 : 3))
                .each(l => { neighbors.add(l.source.id); neighbors.add(l.target.id); });
            node.filter(n => neighbors.has(n.id)).style("opacity", 1)
                .select("circle").attr("r", n => n.id === d.id ? 14 : 10).attr("stroke-width", n => n.id === d.id ? 4 : 2);
        }
        function resetHighlight() {
            node.style("opacity", 1).select("circle").attr("r", 10).attr("stroke-width", 2);
            link.style("opacity", l => l.type === 'mention' ? 0.3 : 1)
                .style("stroke-width", l => {
                    if (l.type === 'ipc' || l.type === 'structural') return 2.5;
                    if (l.type === 'mention') return 1;
                    return 1.5;
                });
        }
        node.append("text").attr("dx", 15).attr("dy", ".35em").attr("fill", "#e2e8f0").attr("font-size", "10px").attr("font-weight", "500").style("pointer-events", "none").text(d => d.label);
        simulation.on("tick", () => {
            link.attr("x1", d => d.source.x).attr("y1", d => d.source.y).attr("x2", d => d.target.x).attr("y2", d => d.target.y);
            node.attr("transform", d => `translate(${d.x},${d.y})`);
        });
        function dragstarted(e, d) { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }
        function dragged(e, d) { d.fx = e.x; d.fy = e.y; }
        function dragended(e, d) { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }
    </script>
</body>
</html>"""
    html = template.replace("__GRAPH_DATA__", json.dumps(graph_data))
    output_file = "scripts/graph.html"
    os.makedirs("scripts", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Graph successfully generated at {os.path.abspath(output_file)}")


if __name__ == "__main__":
    build_project_registry()
    print("Pass 1: Scanning imports...")
    scan_svelte()
    scan_rust()
    scan_python()
    print("Pass 2: Global mention search...")
    perform_global_search()
    build_ipc_edges()
    print("Generating HTML...")
    generate_html()
