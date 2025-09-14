document.addEventListener('DOMContentLoaded', () => {
    const resizer = document.getElementById('resizer');
    const leftPanel = document.getElementById('module-view');
    const rightPanel = document.getElementById('inspector');
    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        document.body.style.userSelect = 'none';
        document.body.style.pointerEvents = 'none';
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', stopResizing);
    });

    const handleMouseMove = (e) => {
        if (!isResizing) return;
        const container = document.getElementById('main-content');
        const containerOffset = container.getBoundingClientRect().left;
        const pointerRelativeX = e.clientX - containerOffset;
        const leftPanelMinWidth = 200;
        const rightPanelMinWidth = 200;
        const newLeftWidth = Math.max(leftPanelMinWidth, pointerRelativeX - (resizer.offsetWidth / 2));
        const newRightWidth = container.offsetWidth - newLeftWidth - resizer.offsetWidth;
        if (newRightWidth >= rightPanelMinWidth) {
            leftPanel.style.flexBasis = `${newLeftWidth}px`;
            rightPanel.style.flexBasis = `${newRightWidth}px`;
        }
    };

    const stopResizing = () => {
        isResizing = false;
        document.body.style.userSelect = '';
        document.body.style.pointerEvents = '';
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', stopResizing);
    };
    
    const sidebar = document.getElementById('sidebar');
    const toggleButton = document.getElementById('sidebar-toggle');
    toggleButton.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
    });

    const searchInput = document.getElementById('search');
    const searchResultsBox = document.getElementById('search-results');
    const moduleHeader = document.getElementById('module-header');
    const treeContainer = document.getElementById('tree-container');
    const inspector = document.getElementById('inspector');
    const treeControls = document.getElementById('tree-controls');

    const expandAllBtn = document.getElementById('expand-all-btn');
    const collapseAllBtn = document.getElementById('collapse-all-btn');

    expandAllBtn.addEventListener('click', () => {
        treeContainer.querySelectorAll('details').forEach(details => details.open = true);
    });

    collapseAllBtn.addEventListener('click', () => {
        treeContainer.querySelectorAll('details').forEach(details => details.open = false);
    });

    const debounce = (func, delay) => {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    };

    const handleSearch = async (event) => {
        const term = event.target.value.trim();
        if (term.length < 2) {
            searchResultsBox.style.display = 'none';
            return;
        }

        const response = await fetch(`/search?term=${encodeURIComponent(term)}`);
        const hits = await response.json();
        searchResultsBox.innerHTML = '';
        if (hits.length > 0) {
            hits.forEach(hit => {
                const div = document.createElement('div');
                div.className = 'search-hit';
                div.innerHTML = `${hit.name} <small>(${hit.module})</small>`;
                div.onclick = () => {
                    loadModule(hit.module, hit.oid);
                    searchInput.value = '';
                    searchResultsBox.style.display = 'none';
                };
                searchResultsBox.appendChild(div);
            });
            searchResultsBox.style.display = 'block';
        } else {
            searchResultsBox.style.display = 'none';
        }
    };

    searchInput.addEventListener('keyup', debounce(handleSearch, 300));

    // --- THIS IS THE CORRECTED FUNCTION ---
    const loadModule = async (moduleName, highlightOid = null) => {
        try {
            const response = await fetch(`/module/${moduleName}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // Render header and clickable imports
            let headerHtml = `<h2>${data.module_identity.name || moduleName}</h2>`;
            if (data.imports && Object.keys(data.imports).length > 0) {
                const importLinks = Object.keys(data.imports).map(mod => `<a href="#" class="import-link" data-module="${mod}">${mod}</a>`).join(', ');
                headerHtml += `<p class="imports-list"><strong>Imports:</strong> ${importLinks}</p>`;
            }
            moduleHeader.innerHTML = headerHtml;

            // Render tree
            const tree = document.createElement('ul');
            tree.className = 'tree';
            tree.innerHTML = renderTree(data.doc);
            treeContainer.innerHTML = ''; // Clear welcome message or old tree
            treeContainer.appendChild(tree);
            treeControls.style.display = 'block';
            
            document.querySelectorAll('.module-list a').forEach(a => {
                a.classList.toggle('active', a.getAttribute('data-module') === moduleName);
            });

            if (highlightOid) {
                const nodeElement = treeContainer.querySelector(`[data-oid='${highlightOid}']`);
                if (nodeElement) {
                    nodeElement.click(); // This will trigger the inspector
                    let parent = nodeElement.closest('details');
                    while (parent) {
                        parent.open = true;
                        parent = parent.parentElement.closest('details');
                    }
                    nodeElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
        } catch (error) {
            console.error("Failed to load module:", moduleName, error);
            treeContainer.innerHTML = `<div class="welcome-message"><p>Error loading module: ${moduleName}. See console for details.</p></div>`;
        }
    };

    const renderTree = (nodes) => {
    let html = '';
    nodes.forEach(node => {
        if (!node || !node.name) return; // Skip invalid nodes

        const hasChildren = node.children && node.children.length > 0;
        const detailsTag = hasChildren ? '<details>' : '';
        const closeDetailsTag = hasChildren ? '</details>' : '';
        const summaryTag = hasChildren ? '<summary>' : '';
        const closeSummaryTag = hasChildren ? '</summary>' : '';

        // Defensively create OID-related attributes only if node.oid exists
        const oidAttr = node.oid ? `data-oid="${node.oid}"` : '';
        const oidDisplay = node.oid ? `(${node.oid.split('.').pop()})` : '(No OID)';

        html += `<li class="tree-node">
            ${detailsTag}
                ${summaryTag}
                    <a href="#" class="node-link" ${oidAttr} data-module="${node.module}">
                        <span class="node-name">${node.name}</span>
                        <span class="node-oid">${oidDisplay}</span>
                    </a>
                ${closeSummaryTag}
                ${hasChildren ? `<ul>${renderTree(node.children)}</ul>` : ''}
            ${closeDetailsTag}
        </li>`;
    });
    return html;
    };
    
    const renderSyntax = (syntax) => {
        if (!syntax) return '';
        const integerMatch = syntax.match(/INTEGER\s*\{(.*?)\}/s);
        if (integerMatch) {
            let table = '<table class="syntax-table"><tr><th>Name</th><th>Value</th></tr>';
            const items = integerMatch[1].matchAll(/(\w+)\s*\((\d+)\)/g);
            for (const item of items) {
                table += `<tr><td>${item[1]}</td><td>${item[2]}</td></tr>`;
            }
            return table + '</table>';
        }
        return `<pre>${escapeHtml(syntax)}</pre>`;
    };

    const showInspector = (nodeData) => {
        let detailsHtml = `<h3>${nodeData.name}</h3>`;
        detailsHtml += `<div class="oid-line"><p><strong>OID:</strong> ${nodeData.oid}</p><button class="copy-btn" data-oid="${nodeData.oid}">Copy</button></div>`;
        if (nodeData.sym_oid) detailsHtml += `<p><strong>Symbolic OID:</strong> ${nodeData.sym_oid}</p>`;
        if (nodeData.klass) detailsHtml += `<p><strong>Class:</strong> ${nodeData.klass}</p>`;
        if (nodeData.syntax) {
            detailsHtml += `<strong>Syntax:</strong> ${renderSyntax(nodeData.syntax)}`;
        }
        if (nodeData.description) {
            detailsHtml += `<strong>Description:</strong><pre>${escapeHtml(nodeData.description)}</pre>`;
        }
        inspector.innerHTML = detailsHtml;
        inspector.style.display = 'block';
    };

    const escapeHtml = (unsafe) => unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    document.addEventListener('click', (e) => {
        if (e.target.closest('.search-results-box')) {
             if (!e.target.closest('.search-hit')) return;
        } else {
             searchResultsBox.style.display = 'none';
        }

        if (e.target.matches('.copy-btn')) {
            const oid = e.target.dataset.oid;
            navigator.clipboard.writeText(oid).then(() => {
                e.target.textContent = 'Copied!';
                setTimeout(() => { e.target.textContent = 'Copy'; }, 2000);
            });
        }
        
        if (e.target.closest('.node-link')) {
            e.preventDefault();
            e.stopPropagation();
            const link = e.target.closest('.node-link');
            const oid = link.dataset.oid;
            const moduleName = link.dataset.module;
            fetch(`/module/${moduleName}?oid=${oid}`)
                .then(response => response.json())
                .then(data => data && showInspector(data));
        }

        if (e.target.closest('.module-list a')) {
            e.preventDefault();
            const link = e.target.closest('.module-list a');
            loadModule(link.dataset.module);
            inspector.style.display = 'none';
        }
        
        if (e.target.matches('.import-link')) {
            e.preventDefault();
            loadModule(e.target.dataset.module);
        }
    });
});
