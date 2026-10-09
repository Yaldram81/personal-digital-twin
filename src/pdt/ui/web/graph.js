/**
 * Belief Network Graph Visualizer
 * High-performance, interactive HTML5 Canvas force-directed graph.
 */

class BeliefGraphVisualizer {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    this.onSelectNode = options.onSelectNode || (() => {});
    this.nodes = [];
    this.edges = [];
    this.domainFilter = 'all';

    // Camera transform
    this.transform = { x: 0, y: 0, scale: 1 };
    this.isDragging = false;
    this.dragStart = { x: 0, y: 0 };
    this.selectedNode = null;
    this.hoveredNode = null;
    this.draggedNode = null;

    this.domainColors = {
      career: '#6366f1',
      ethics: '#06b6d4',
      finance: '#10b981',
      personal: '#8b5cf6',
      health: '#f59e0b',
      technology: '#38bdf8',
      relationships: '#ec4899',
      general: '#94a3b8'
    };

    this.initCanvasSize();
    this.attachEventListeners();
    this.startAnimationLoop();
  }

  initCanvasSize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.width = rect.width;
    this.height = rect.height;
    this.transform.x = this.width / 2;
    this.transform.y = this.height / 2;
  }

  setData(nodes, edges) {
    // Keep existing positions if node exists to avoid jarring jumps
    const existingMap = new Map(this.nodes.map(n => [n.id, n]));

    this.nodes = nodes.map((node, i) => {
      const existing = existingMap.get(node.id);
      const angle = (i / Math.max(1, nodes.length)) * Math.PI * 2;
      const radius = 120 + (i % 3) * 60;
      return {
        id: node.id,
        statement: node.statement,
        domain: (node.domain || 'general').toLowerCase(),
        confidence: typeof node.confidence === 'object' ? node.confidence.estimate : (node.confidence || 0.75),
        confidenceObj: node.confidence,
        evidenceCount: node.evidence_count || 1,
        x: existing ? existing.x : Math.cos(angle) * radius,
        y: existing ? existing.y : Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        radius: 14 + Math.min(16, (node.evidence_count || 1) * 3)
      };
    });

    this.edges = edges.map(edge => ({
      source: edge.source,
      target: edge.target,
      relationship: edge.relationship || 'supports',
      weight: edge.weight || 1
    }));
  }

  setDomainFilter(domain) {
    this.domainFilter = domain.toLowerCase();
  }

  attachEventListeners() {
    window.addEventListener('resize', () => this.initCanvasSize());

    this.canvas.addEventListener('mousedown', (e) => {
      const pos = this.getCanvasCoords(e);
      const clicked = this.findNodeAt(pos.x, pos.y);

      if (clicked) {
        this.draggedNode = clicked;
        this.selectedNode = clicked;
        this.onSelectNode(clicked);
      } else {
        this.isDragging = true;
        this.dragStart = { x: e.clientX - this.transform.x, y: e.clientY - this.transform.y };
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (this.draggedNode) {
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = (e.clientX - rect.left - this.transform.x) / this.transform.scale;
        const mouseY = (e.clientY - rect.top - this.transform.y) / this.transform.scale;
        this.draggedNode.x = mouseX;
        this.draggedNode.y = mouseY;
        return;
      }

      if (this.isDragging) {
        this.transform.x = e.clientX - this.dragStart.x;
        this.transform.y = e.clientY - this.dragStart.y;
        return;
      }

      const pos = this.getCanvasCoords(e);
      const node = this.findNodeAt(pos.x, pos.y);
      if (node !== this.hoveredNode) {
        this.hoveredNode = node;
        this.canvas.style.cursor = node ? 'pointer' : 'default';
      }
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
      this.draggedNode = null;
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
      this.transform.scale = Math.max(0.3, Math.min(2.5, this.transform.scale * zoomFactor));
    });
  }

  getCanvasCoords(e) {
    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - this.transform.x) / this.transform.scale;
    const y = (e.clientY - rect.top - this.transform.y) / this.transform.scale;
    return { x, y };
  }

  findNodeAt(x, y) {
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const node = this.nodes[i];
      if (this.domainFilter !== 'all' && node.domain !== this.domainFilter) continue;
      const dx = node.x - x;
      const dy = node.y - y;
      if (dx * dx + dy * dy <= node.radius * node.radius) {
        return node;
      }
    }
    return null;
  }

  updatePhysics() {
    const visibleNodes = this.nodes.filter(
      n => this.domainFilter === 'all' || n.domain === this.domainFilter
    );
    const nodeMap = new Map(visibleNodes.map(n => [n.id, n]));

    // Repulsion between visible nodes
    for (let i = 0; i < visibleNodes.length; i++) {
      for (let j = i + 1; j < visibleNodes.length; j++) {
        const a = visibleNodes[i];
        const b = visibleNodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        if (dist < 220) {
          const force = (220 - dist) / dist * 0.4;
          if (a !== this.draggedNode) { a.x -= dx * force * 0.1; a.y -= dy * force * 0.1; }
          if (b !== this.draggedNode) { b.x += dx * force * 0.1; b.y += dy * force * 0.1; }
        }
      }
    }

    // Spring attraction along edges
    for (const edge of this.edges) {
      const a = nodeMap.get(edge.source);
      const b = nodeMap.get(edge.target);
      if (!a || !b) continue;

      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const targetDist = 140;
      const force = (dist - targetDist) * 0.02;

      if (a !== this.draggedNode) { a.x += dx / dist * force; a.y += dy / dist * force; }
      if (b !== this.draggedNode) { b.x -= dx / dist * force; b.y -= dy / dist * force; }
    }

    // Weak gravitational centering pull
    for (const node of visibleNodes) {
      if (node === this.draggedNode) continue;
      node.x *= 0.985;
      node.y *= 0.985;
    }
  }

  startAnimationLoop() {
    const loop = () => {
      this.updatePhysics();
      this.render();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  render() {
    this.ctx.save();
    this.ctx.clearRect(0, 0, this.width, this.height);

    // Apply camera pan & zoom
    this.ctx.translate(this.transform.x, this.transform.y);
    this.ctx.scale(this.transform.scale, this.transform.scale);

    const visibleNodes = this.nodes.filter(
      n => this.domainFilter === 'all' || n.domain === this.domainFilter
    );
    const nodeMap = new Map(visibleNodes.map(n => [n.id, n]));

    // Draw Edges
    for (const edge of this.edges) {
      const a = nodeMap.get(edge.source);
      const b = nodeMap.get(edge.target);
      if (!a || !b) continue;

      this.ctx.beginPath();
      this.ctx.moveTo(a.x, a.y);
      this.ctx.lineTo(b.x, b.y);

      if (edge.relationship === 'tension') {
        this.ctx.strokeStyle = 'rgba(244, 63, 94, 0.55)';
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([4, 4]);
      } else {
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
        this.ctx.lineWidth = 1.5;
        this.ctx.setLineDash([]);
      }
      this.ctx.stroke();
    }
    this.ctx.setLineDash([]);

    // Draw Nodes
    for (const node of visibleNodes) {
      const isSelected = this.selectedNode && this.selectedNode.id === node.id;
      const isHovered = this.hoveredNode && this.hoveredNode.id === node.id;
      const color = this.domainColors[node.domain] || this.domainColors.general;

      // Glow circle on hover or selection
      if (isSelected || isHovered) {
        this.ctx.beginPath();
        this.ctx.arc(node.x, node.y, node.radius + 8, 0, Math.PI * 2);
        this.ctx.fillStyle = isSelected ? 'rgba(99, 102, 241, 0.35)' : 'rgba(255, 255, 255, 0.15)';
        this.ctx.fill();
      }

      // Outer border circle
      this.ctx.beginPath();
      this.ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      this.ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
      this.ctx.fill();
      this.ctx.lineWidth = 2.5;
      this.ctx.strokeStyle = color;
      this.ctx.stroke();

      // Inner pulse dot
      this.ctx.beginPath();
      this.ctx.arc(node.x, node.y, 4, 0, Math.PI * 2);
      this.ctx.fillStyle = color;
      this.ctx.fill();

      // Node Label
      const shortText = node.statement.length > 22
        ? node.statement.slice(0, 20) + '...'
        : node.statement;

      this.ctx.font = '500 11px "Plus Jakarta Sans", system-ui, sans-serif';
      this.ctx.fillStyle = isSelected ? '#ffffff' : '#94a3b8';
      this.ctx.textAlign = 'center';
      this.ctx.fillText(shortText, node.x, node.y + node.radius + 14);

      // Confidence badge
      const confText = Math.round(node.confidence * 100) + '%';
      this.ctx.font = '600 9px "JetBrains Mono", monospace';
      this.ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
      this.ctx.fillText(confText, node.x, node.y + node.radius + 26);
    }

    this.ctx.restore();
  }

  zoomIn() {
    this.transform.scale = Math.min(2.5, this.transform.scale * 1.25);
  }

  zoomOut() {
    this.transform.scale = Math.max(0.3, this.transform.scale / 1.25);
  }

  resetCamera() {
    this.transform = { x: this.width / 2, y: this.height / 2, scale: 1 };
  }
}

window.BeliefGraphVisualizer = BeliefGraphVisualizer;
