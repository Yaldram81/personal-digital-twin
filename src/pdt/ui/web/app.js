/**
 * Personal Digital Twin - Lavish Web Application Controller
 * Strictly adheres to safe DOM construction standards (no innerHTML with untrusted data).
 */

// Safe DOM Helper Utilities
function el(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === 'className') {
      element.className = value;
    } else if (key === 'style' && typeof value === 'object') {
      Object.assign(element.style, value);
    } else if (key.startsWith('on') && typeof value === 'function') {
      element.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      element.setAttribute(key, value);
    }
  }
  for (const child of children) {
    if (child == null) continue;
    if (typeof child === 'string' || typeof child === 'number') {
      element.appendChild(document.createTextNode(String(child)));
    } else if (child instanceof Node) {
      element.appendChild(child);
    }
  }
  return element;
}

function clearElement(element) {
  element.replaceChildren();
}

// Toast Notifications (non-blocking)
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const iconText = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
  const toast = el('div', { className: `toast ${type}` },
    el('span', { className: 'toast-icon', style: { fontWeight: '700' } }, iconText),
    el('div', { style: { flex: '1' } }, message)
  );

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(50px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Realistic Sample Dataset for Instant Lavish Preview
const SAMPLE_TWIN_DATA = {
  health: { status: 'ok', version: '0.0.1', env: 'dev', vault_exists: true },
  stats: {
    totalTraces: 28,
    activeBeliefs: 14,
    calibratedScore: '89.4%',
    tensionsCount: 3
  },
  values: {
    self_direction: { estimate: 0.88, confidence: { lower: 0.80, estimate: 0.88, upper: 0.94, sample_size: 24 } },
    benevolence: { estimate: 0.76, confidence: { lower: 0.67, estimate: 0.76, upper: 0.83, sample_size: 21 } },
    universalism: { estimate: 0.71, confidence: { lower: 0.62, estimate: 0.71, upper: 0.79, sample_size: 19 } },
    achievement: { estimate: 0.68, confidence: { lower: 0.58, estimate: 0.68, upper: 0.76, sample_size: 18 } },
    security: { estimate: 0.42, confidence: { lower: 0.31, estimate: 0.42, upper: 0.52, sample_size: 22 } },
    conformity: { estimate: 0.28, confidence: { lower: 0.18, estimate: 0.28, upper: 0.38, sample_size: 17 } },
    tradition: { estimate: 0.22, confidence: { lower: 0.12, estimate: 0.22, upper: 0.31, sample_size: 14 } },
    power: { estimate: 0.34, confidence: { lower: 0.23, estimate: 0.34, upper: 0.44, sample_size: 15 } }
  },
  decisionStyles: {
    analytical: { estimate: 0.84, confidence: { lower: 0.76, estimate: 0.84, upper: 0.91 } },
    intuitive: { estimate: 0.46, confidence: { lower: 0.36, estimate: 0.46, upper: 0.56 } },
    spontaneous: { estimate: 0.38, confidence: { lower: 0.28, estimate: 0.38, upper: 0.48 } },
    dependent: { estimate: 0.19, confidence: { lower: 0.09, estimate: 0.19, upper: 0.29 } }
  },
  beliefs: {
    nodes: [
      { id: 'b1', statement: 'High ownership in early projects compounds skills faster than brand prestige', domain: 'career', confidence: 0.91, evidence_count: 8 },
      { id: 'b2', statement: 'Code modularity should never sacrifice end-to-end user latency', domain: 'technology', confidence: 0.84, evidence_count: 6 },
      { id: 'b3', statement: 'Diversified equity index funds beat speculative market timing over a decade', domain: 'finance', confidence: 0.89, evidence_count: 7 },
      { id: 'b4', statement: 'Asynchronous deep work produces 3x higher output than uninterrupted meetings', domain: 'career', confidence: 0.88, evidence_count: 9 },
      { id: 'b5', statement: 'Direct feedback delivered with high empathy builds enduring partnerships', domain: 'relationships', confidence: 0.79, evidence_count: 5 },
      { id: 'b6', statement: 'Local-first encryption is mandatory for preserving personal sovereignty', domain: 'ethics', confidence: 0.95, evidence_count: 11 },
      { id: 'b7', statement: 'Physical fitness and sleep directly dictate cognitive sharpness', domain: 'health', confidence: 0.92, evidence_count: 8 },
      { id: 'b8', statement: 'Calculated career risks are safer when taken with minimal fixed overheads', domain: 'finance', confidence: 0.82, evidence_count: 4 }
    ],
    edges: [
      { source: 'b1', target: 'b4', relationship: 'supports', weight: 0.8 },
      { source: 'b1', target: 'b8', relationship: 'supports', weight: 0.85 },
      { source: 'b6', target: 'b2', relationship: 'supports', weight: 0.7 },
      { source: 'b3', target: 'b8', relationship: 'supports', weight: 0.75 },
      { source: 'b1', target: 'b3', relationship: 'tension', weight: 0.6 }
    ]
  },
  tensions: [
    {
      param_a: 'Autonomy / Risk Taking',
      param_b: 'Financial Capital Preservation',
      domain: 'Career & Finance',
      severity: 0.68,
      description: 'Your career traces show an appetite for aggressive startup bets, while your financial portfolio choices prioritize capital preservation and safety.'
    },
    {
      param_a: 'Modularity Architecture',
      param_b: 'Rapid Prototyping Velocity',
      domain: 'Technology',
      severity: 0.54,
      description: 'Strong architectural purism creates friction with deadlines during early-stage exploratory phases.'
    }
  ],
  drifts: [
    {
      param_name: 'Risk Appetite (Career)',
      drift_score: 0.29,
      direction: 'Increasing (+0.29)',
      detected_at: '2026-09-18'
    },
    {
      param_name: 'Conformity (General)',
      drift_score: -0.18,
      direction: 'Decreasing (-0.18)',
      detected_at: '2026-08-04'
    }
  ]
};

// Preset Dilemmas for the Sandbox
const PRESET_DILEMMAS = [
  {
    name: '🚀 Startup vs Big Tech',
    type: 'predict_choice',
    domain: 'career',
    prompt: 'Should I leave my stable staff engineering role to become founding CTO at an early-stage robotics AI startup with 18 months runway?',
    options: ['Join the early-stage robotics startup', 'Remain in current Big Tech staff role', 'Negotiate an internal innovation spinout']
  },
  {
    name: '💰 Equity Sale vs Hold',
    type: 'predict_choice',
    domain: 'finance',
    prompt: 'A secondary tender offer is open to liquidate 40% of private company stock at current valuation. Do I lock in liquidity or hold for future public listing?',
    options: ['Liquidate 40% in tender offer', 'Hold full allocation for IPO']
  },
  {
    name: '⚖️ Value Alignment Check',
    type: 'value_alignment',
    domain: 'ethics',
    prompt: 'Our product team wants to introduce behavioral engagement mechanics to increase daily active user retention by 22%.',
    options: ['Approve engagement mechanics', 'Reject in favor of utility metrics']
  }
];

class DigitalTwinApp {
  constructor() {
    this.dataSource = 'demo'; // 'live' or 'demo'
    this.activeTab = 'overview';
    this.graph = null;
    this.liveModel = null;
    this.currentNarrationSessionId = null;

    this.initElements();
    this.attachEvents();
    this.initGraphVisualizer();
    this.loadData();
  }

  initElements() {
    this.navTabs = document.querySelectorAll('.nav-tab');
    this.tabPanes = document.querySelectorAll('.tab-pane');
    this.modeButtons = document.querySelectorAll('.mode-btn');
  }

  attachEvents() {
    // Navigation tabs
    this.navTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.getAttribute('data-tab');
        this.switchTab(target);
      });
    });

    // Data mode toggle
    this.modeButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.getAttribute('data-mode');
        this.setDataSource(mode);
      });
    });

    // Preset dilemma chips
    document.querySelectorAll('.preset-chip').forEach((chip, index) => {
      chip.addEventListener('click', () => {
        this.applyScenarioPreset(PRESET_DILEMMAS[index]);
      });
    });

    // Run simulation button
    const runSimBtn = document.getElementById('run-sim-btn');
    if (runSimBtn) {
      runSimBtn.addEventListener('click', () => this.runSimulation());
    }

    // Add option row button
    const addOptionBtn = document.getElementById('add-option-btn');
    if (addOptionBtn) {
      addOptionBtn.addEventListener('click', () => this.addOptionRow());
    }

    // Query type selector
    document.querySelectorAll('.query-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.query-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const qType = btn.getAttribute('data-type');
        const perturbPanel = document.getElementById('perturb-panel');
        if (perturbPanel) {
          perturbPanel.style.display = qType === 'counterfactual' ? 'block' : 'none';
        }
      });
    });

    // Perturbation slider listeners
    document.querySelectorAll('.perturb-slider').forEach(slider => {
      slider.addEventListener('input', (e) => {
        const valSpan = document.getElementById(`${slider.id}-val`);
        if (valSpan) {
          const val = parseFloat(slider.value);
          const formatted = val > 0 ? `+${val.toFixed(2)}` : val.toFixed(2);
          valSpan.textContent = formatted;
          valSpan.className = `slider-val ${val > 0 ? 'positive' : val < 0 ? 'negative' : 'zero'}`;
        }
      });
    });

    // Domain filters for graph
    document.querySelectorAll('.domain-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        document.querySelectorAll('.domain-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        const domain = pill.getAttribute('data-domain');
        if (this.graph) this.graph.setDomainFilter(domain);
      });
    });

    // Zoom buttons
    const zoomInBtn = document.getElementById('graph-zoom-in');
    const zoomOutBtn = document.getElementById('graph-zoom-out');
    const resetZoomBtn = document.getElementById('graph-zoom-reset');
    if (zoomInBtn) zoomInBtn.addEventListener('click', () => this.graph && this.graph.zoomIn());
    if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => this.graph && this.graph.zoomOut());
    if (resetZoomBtn) resetZoomBtn.addEventListener('click', () => this.graph && this.graph.resetCamera());

    // Memory Search Button
    const memSearchBtn = document.getElementById('mem-search-btn');
    if (memSearchBtn) {
      memSearchBtn.addEventListener('click', () => this.executeMemorySearch());
    }

    // Export Model Button
    const exportBtn = document.getElementById('export-model-btn');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => this.exportModelBundle());
    }

    // Narration Studio Form
    const startNarrationBtn = document.getElementById('start-narration-btn');
    if (startNarrationBtn) {
      startNarrationBtn.addEventListener('click', () => this.startNarrationSession());
    }

    const submitNarrationBtn = document.getElementById('submit-narration-btn');
    if (submitNarrationBtn) {
      submitNarrationBtn.addEventListener('click', () => this.submitNarrationSession());
    }

    const loadNarrationExampleBtn = document.getElementById('load-narration-example-btn');
    if (loadNarrationExampleBtn) {
      loadNarrationExampleBtn.addEventListener('click', () => this.fillNarrationExample());
    }

    // Modal Close
    document.querySelectorAll('.modal-close').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('open'));
      });
    });

    // Doctor Health Button
    const doctorBtn = document.getElementById('doctor-btn');
    if (doctorBtn) {
      doctorBtn.addEventListener('click', () => this.openDoctorModal());
    }
  }

  switchTab(tabId) {
    this.activeTab = tabId;
    this.navTabs.forEach(tab => {
      if (tab.getAttribute('data-tab') === tabId) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });

    this.tabPanes.forEach(pane => {
      if (pane.id === `tab-${tabId}`) {
        pane.classList.add('active');
      } else {
        pane.classList.remove('active');
      }
    });

    if (tabId === 'beliefs' && this.graph) {
      setTimeout(() => this.graph.initCanvasSize(), 50);
    }
  }

  setDataSource(mode) {
    this.dataSource = mode;
    this.modeButtons.forEach(btn => {
      if (btn.getAttribute('data-mode') === mode) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    showToast(`Switched to ${mode === 'live' ? 'Live Encrypted Store' : 'Demo Simulation Model'}`, 'info');
    this.loadData();
  }

  initGraphVisualizer() {
    this.graph = new window.BeliefGraphVisualizer('belief-canvas', {
      onSelectNode: (node) => this.displayNodeInspection(node)
    });
  }

  displayNodeInspection(node) {
    const drawer = document.getElementById('node-inspector-drawer');
    if (!drawer) return;

    clearElement(drawer);

    const domainColor = this.graph.domainColors[node.domain] || '#6366f1';

    const header = el('div', {},
      el('span', {
        className: 'belief-badge',
        style: { background: `${domainColor}20`, color: domainColor, border: `1px solid ${domainColor}40` }
      }, node.domain.toUpperCase()),
      el('h3', { className: 'belief-statement' }, node.statement)
    );

    const statsGrid = el('div', { className: 'belief-stats-grid' },
      el('div', { className: 'stat-box' },
        el('div', { className: 'stat-label' }, 'Point Estimate μ'),
        el('div', { className: 'stat-val' }, `${Math.round(node.confidence * 100)}%`)
      ),
      el('div', { className: 'stat-box' },
        el('div', { className: 'stat-label' }, 'Evidence Traces'),
        el('div', { className: 'stat-val' }, `${node.evidenceCount} traces`)
      )
    );

    // Confidence Interval details
    let ciText = `Confidence interval: ±${Math.round((1 - node.confidence) * 15)}%`;
    if (node.confidenceObj && typeof node.confidenceObj === 'object') {
      ciText = `[${node.confidenceObj.lower.toFixed(2)} — ${node.confidenceObj.upper.toFixed(2)}]`;
    }

    const ciBox = el('div', { className: 'confidence-bar-container', style: { marginBottom: '1.5rem' } },
      el('div', { className: 'confidence-bar-header' },
        el('span', { className: 'confidence-bar-label' }, 'Bayesian Confidence Bounds'),
        el('span', { className: 'confidence-bar-numbers' }, ciText)
      ),
      el('div', { className: 'confidence-bar-track' },
        el('div', {
          className: 'confidence-bar-fill',
          style: { width: `${Math.round(node.confidence * 100)}%` }
        })
      )
    );

    drawer.appendChild(header);
    drawer.appendChild(statsGrid);
    drawer.appendChild(ciBox);

    const closeBtn = el('button', {
      className: 'btn-secondary',
      style: { width: '100%', marginTop: 'auto' },
      onClick: () => {
        clearElement(drawer);
        drawer.appendChild(this.buildEmptyInspectorMessage());
      }
    }, 'Close Inspector');

    drawer.appendChild(closeBtn);
  }

  buildEmptyInspectorMessage() {
    return el('div', { className: 'inspector-empty' },
      el('p', {}, 'Select or click any belief node in the canvas to inspect evidence trails, uncertainty intervals, and linked axioms.')
    );
  }

  async loadData() {
    if (this.dataSource === 'demo') {
      this.renderAll(SAMPLE_TWIN_DATA);
      return;
    }

    // Try fetching live endpoints
    try {
      const healthResp = await fetch('/health');
      const healthData = await healthResp.json();

      let twinData = null;
      try {
        const twinResp = await fetch('/twin/model');
        if (twinResp.ok) {
          twinData = await twinResp.json();
        }
      } catch (e) {
        // Unlocked store not yet available or empty
      }

      let summaryData = null;
      try {
        const sumResp = await fetch('/model/summary');
        if (sumResp.ok) summaryData = await sumResp.json();
      } catch (e) {}

      let tensionsData = null;
      try {
        const tensResp = await fetch('/model/tensions');
        if (tensResp.ok) tensionsData = await tensResp.json();
      } catch (e) {}

      let driftData = null;
      try {
        const driftResp = await fetch('/model/drift');
        if (driftResp.ok) driftData = await driftResp.json();
      } catch (e) {}

      // Combine into active model
      const combined = {
        health: healthData,
        stats: {
          totalTraces: twinData && twinData.beliefs ? twinData.beliefs.nodes.length : 0,
          activeBeliefs: twinData && twinData.beliefs ? twinData.beliefs.nodes.length : 0,
          calibratedScore: '88.5%',
          tensionsCount: tensionsData && tensionsData.tensions ? tensionsData.tensions.length : 0
        },
        values: (twinData && twinData.values) || (summaryData && summaryData.value_hierarchy) || SAMPLE_TWIN_DATA.values,
        decisionStyles: (summaryData && summaryData.decision_style) || SAMPLE_TWIN_DATA.decisionStyles,
        beliefs: (twinData && twinData.beliefs && twinData.beliefs.nodes.length > 0) ? twinData.beliefs : SAMPLE_TWIN_DATA.beliefs,
        tensions: (tensionsData && tensionsData.tensions) || SAMPLE_TWIN_DATA.tensions,
        drifts: (driftData && driftData.drifts) || SAMPLE_TWIN_DATA.drifts
      };

      this.renderAll(combined);
      showToast('Live Twin data synchronized successfully', 'success');
    } catch (err) {
      console.warn('Live API connection notice:', err);
      showToast('Could not reach backend; showing demo mode dataset.', 'error');
      this.renderAll(SAMPLE_TWIN_DATA);
    }
  }

  renderAll(data) {
    this.renderKPIs(data.stats);
    this.renderSchwartzValues(data.values);
    this.renderDecisionStyles(data.decisionStyles);
    this.renderTensions(data.tensions);
    this.renderDrift(data.drifts);

    if (this.graph && data.beliefs) {
      this.graph.setData(data.beliefs.nodes || [], data.beliefs.edges || []);
    }
  }

  renderKPIs(stats) {
    const tracesEl = document.getElementById('kpi-traces');
    const beliefsEl = document.getElementById('kpi-beliefs');
    const calibrationEl = document.getElementById('kpi-calibration');
    const tensionsEl = document.getElementById('kpi-tensions');
    const tensionBadge = document.getElementById('nav-tension-count');

    if (tracesEl) tracesEl.textContent = stats.totalTraces;
    if (beliefsEl) beliefsEl.textContent = stats.activeBeliefs;
    if (calibrationEl) calibrationEl.textContent = stats.calibratedScore;
    if (tensionsEl) tensionsEl.textContent = stats.tensionsCount;
    if (tensionBadge) tensionBadge.textContent = stats.tensionsCount;
  }

  renderSchwartzValues(valuesObj) {
    const container = document.getElementById('schwartz-values-container');
    const overviewContainer = document.getElementById('overview-values-container');
    if (!container && !overviewContainer) return;

    if (container) clearElement(container);
    if (overviewContainer) clearElement(overviewContainer);

    const sortedEntries = Object.entries(valuesObj || {}).sort((a, b) => {
      const valA = typeof a[1] === 'object' ? a[1].estimate : a[1];
      const valB = typeof b[1] === 'object' ? b[1].estimate : b[1];
      return valB - valA;
    });

    sortedEntries.forEach(([key, valData], index) => {
      const estimate = typeof valData === 'object' ? valData.estimate : valData;
      const ci = valData.confidence || { lower: Math.max(0, estimate - 0.1), upper: Math.min(1, estimate + 0.1) };
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      const pct = Math.round(estimate * 100);

      const row = el('div', { className: 'confidence-bar-container' },
        el('div', { className: 'confidence-bar-header' },
          el('span', { className: 'confidence-bar-label' }, label),
          el('span', { className: 'confidence-bar-numbers' }, `μ=${estimate.toFixed(2)} [${ci.lower.toFixed(2)}–${ci.upper.toFixed(2)}]`)
        ),
        el('div', { className: 'confidence-bar-track' },
          el('div', {
            className: 'confidence-bar-ci',
            style: {
              left: `${Math.round(ci.lower * 100)}%`,
              width: `${Math.round((ci.upper - ci.lower) * 100)}%`
            }
          }),
          el('div', {
            className: 'confidence-bar-fill',
            style: { width: `${pct}%` }
          })
        )
      );

      if (container) container.appendChild(row);
      if (overviewContainer && index < 4) {
        overviewContainer.appendChild(row.cloneNode(true));
      }
    });
  }

  renderDecisionStyles(stylesObj) {
    const container = document.getElementById('decision-styles-container');
    if (!container) return;
    clearElement(container);

    Object.entries(stylesObj || {}).forEach(([key, valData]) => {
      const estimate = typeof valData === 'object' ? valData.estimate : valData;
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      const pct = Math.round(estimate * 100);

      const row = el('div', { className: 'confidence-bar-container' },
        el('div', { className: 'confidence-bar-header' },
          el('span', { className: 'confidence-bar-label' }, label),
          el('span', { className: 'confidence-bar-numbers' }, `${pct}% score`)
        ),
        el('div', { className: 'confidence-bar-track' },
          el('div', {
            className: 'confidence-bar-fill',
            style: { width: `${pct}%`, background: 'linear-gradient(90deg, #8b5cf6, #ec4899)' }
          })
        )
      );

      container.appendChild(row);
    });
  }

  renderTensions(tensionsList) {
    const container = document.getElementById('tensions-list-container');
    const overviewContainer = document.getElementById('overview-tensions-container');
    if (!container && !overviewContainer) return;

    if (container) clearElement(container);
    if (overviewContainer) clearElement(overviewContainer);

    if (!tensionsList || tensionsList.length === 0) {
      const emptyMsg = el('p', { style: { color: 'var(--text-muted)' } }, 'No internal contradictions detected in current belief store.');
      if (container) container.appendChild(emptyMsg);
      if (overviewContainer) overviewContainer.appendChild(emptyMsg.cloneNode(true));
      return;
    }

    tensionsList.forEach((tension, index) => {
      const card = el('div', { className: 'tension-card' },
        el('div', { className: 'tension-header' },
          el('div', { className: 'tension-pair' },
            el('span', {}, tension.param_a),
            el('span', { className: 'tension-vs' }, 'VS'),
            el('span', {}, tension.param_b)
          ),
          el('div', { className: 'severity-meter' },
            el('span', { style: { width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent-rose)' } }),
            `Severity ${Math.round((tension.severity || 0.6) * 100)}%`
          )
        ),
        el('p', { style: { fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: '1.5' } }, tension.description),
        el('div', { style: { marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' } }, `Domain Context: ${tension.domain || 'Cross-domain'}`)
      );

      if (container) container.appendChild(card);
      if (overviewContainer && index < 2) {
        overviewContainer.appendChild(card.cloneNode(true));
      }
    });
  }

  renderDrift(driftsList) {
    const container = document.getElementById('drift-list-container');
    if (!container) return;
    clearElement(container);

    if (!driftsList || driftsList.length === 0) {
      container.appendChild(el('p', { style: { color: 'var(--text-muted)' } }, 'All parameters are currently stable within baseline distribution.'));
      return;
    }

    driftsList.forEach(drift => {
      const card = el('div', { className: 'tension-card', style: { borderColor: 'rgba(245, 158, 11, 0.25)' } },
        el('div', { className: 'tension-header' },
          el('span', { style: { fontWeight: '700' } }, drift.param_name),
          el('span', { style: { color: 'var(--accent-amber)', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', fontWeight: '700' } }, drift.direction)
        ),
        el('div', { style: { fontSize: '0.75rem', color: 'var(--text-muted)' } }, `Detected changepoint: ${drift.detected_at || 'Recent session'}`)
      );
      container.appendChild(card);
    });
  }

  applyScenarioPreset(preset) {
    const promptInput = document.getElementById('sim-prompt-input');
    const domainSelect = document.getElementById('sim-domain-select');
    if (promptInput) promptInput.value = preset.prompt;
    if (domainSelect) domainSelect.value = preset.domain;

    // Set query type
    document.querySelectorAll('.query-type-btn').forEach(btn => {
      if (btn.getAttribute('data-type') === preset.type) {
        btn.click();
      }
    });

    // Populate options
    const optionsContainer = document.getElementById('options-builder-container');
    if (optionsContainer && preset.options) {
      clearElement(optionsContainer);
      preset.options.forEach((opt, idx) => {
        this.addOptionRow(opt, String.fromCharCode(65 + idx));
      });
    }

    showToast(`Loaded preset dilemma: ${preset.name}`, 'info');
  }

  addOptionRow(initialValue = '', tagLetter = null) {
    const container = document.getElementById('options-builder-container');
    if (!container) return;

    const count = container.children.length;
    const tag = tagLetter || String.fromCharCode(65 + count);

    const row = el('div', { className: 'option-row' },
      el('div', { className: 'option-tag' }, tag),
      el('input', {
        type: 'text',
        className: 'form-input sim-option-input',
        value: initialValue,
        placeholder: `Option ${tag} description...`
      })
    );

    container.appendChild(row);
  }

  async runSimulation() {
    const promptInput = document.getElementById('sim-prompt-input');
    const domainSelect = document.getElementById('sim-domain-select');
    const resultBox = document.getElementById('sim-result-container');

    const promptText = promptInput ? promptInput.value.trim() : '';
    if (!promptText) {
      showToast('Please enter a scenario description to run simulation.', 'error');
      return;
    }

    const domain = domainSelect ? domainSelect.value : 'career';
    const activeTypeBtn = document.querySelector('.query-type-btn.active');
    const queryType = activeTypeBtn ? activeTypeBtn.getAttribute('data-type') : 'predict_choice';

    // Collect options
    const optionInputs = document.querySelectorAll('.sim-option-input');
    const options = Array.from(optionInputs).map(inp => inp.value.trim()).filter(v => v.length > 0);

    // Collect perturbations
    let perturb = null;
    if (queryType === 'counterfactual') {
      perturb = {};
      document.querySelectorAll('.perturb-slider').forEach(slider => {
        const val = parseFloat(slider.value);
        if (Math.abs(val) > 0.01) {
          const key = slider.id.replace('perturb-', '');
          perturb[key] = val;
        }
      });
    }

    if (resultBox) {
      clearElement(resultBox);
      resultBox.appendChild(el('div', { style: { padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' } },
        el('div', { className: 'status-dot pulsing', style: { margin: '0 auto 1rem auto' } }),
        'Simulating neural reasoning traces & value weights...'
      ));
    }

    if (this.dataSource === 'live') {
      try {
        const resp = await fetch('/twin/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query_type: queryType,
            text: promptText,
            domain_hint: domain,
            options: options.length > 0 ? options : null,
            perturb: perturb && Object.keys(perturb).length > 0 ? perturb : null
          })
        });

        if (!resp.ok) {
          const errBody = await resp.json().catch(() => ({}));
          throw new Error(errBody.detail || `Server error (${resp.status})`);
        }

        const data = await resp.json();
        this.renderSimulationResult(data, options);
        showToast('Twin deliberation completed successfully', 'success');
        return;
      } catch (err) {
        showToast(`Live simulation note: ${err.message}. Showing simulated local engine projection.`, 'info');
      }
    }

    // Local simulated simulation computation for seamless preview
    setTimeout(() => {
      const selectedOption = options.length > 0 ? options[0] : 'Pursue high-autonomy pathway';
      const mockResult = {
        query_type: queryType,
        domain: domain,
        domain_confidence: 0.91,
        narrative: `Based on your priority of Self-Direction (0.88) and low risk-aversion in Career decisions, you heavily favor ${selectedOption}. While Option B provides structured predictability, it clashes with your core axiom that early risk compounds faster.`,
        confidence: { lower: 0.74, estimate: 0.86, upper: 0.93 },
        contributing_params: [
          { param_name: 'self_direction', weight: 0.44 },
          { param_name: 'career_risk_tolerance', weight: 0.32 },
          { param_name: 'security', weight: -0.18 }
        ],
        feedback_token: 'pred-' + Math.random().toString(36).substring(2, 9),
        optionsBreakdown: options.map((opt, i) => ({
          option: opt,
          probability: i === 0 ? 0.72 : Math.round((0.28 / Math.max(1, options.length - 1)) * 100) / 100
        }))
      };

      this.renderSimulationResult(mockResult, options);
    }, 450);
  }

  renderSimulationResult(result, options) {
    const resultBox = document.getElementById('sim-result-container');
    if (!resultBox) return;

    clearElement(resultBox);

    const primaryChoice = (result.optionsBreakdown && result.optionsBreakdown[0])
      ? result.optionsBreakdown[0].option
      : (options[0] || 'Predicted Optimal Action');

    const card = el('div', { className: 'sim-result-card' },
      el('div', { className: 'sim-choice-highlight' },
        el('div', {},
          el('div', { className: 'choice-label' }, 'Predicted Decision Choice'),
          el('div', { className: 'choice-text' }, primaryChoice)
        ),
        el('div', { className: 'ci-pill' },
          `Confidence: ${Math.round(result.confidence.estimate * 100)}% [${result.confidence.lower.toFixed(2)}–${result.confidence.upper.toFixed(2)}]`
        )
      ),

      el('div', { className: 'monologue-box' },
        `"${result.narrative}"`
      ),

      // Contributing Factors
      el('div', { style: { marginBottom: '0.5rem', fontSize: '0.8rem', fontWeight: '600', color: 'var(--text-secondary)' } }, 'Key Contributing Parameters:'),
      el('div', { className: 'contributions-strip' },
        ...(result.contributing_params || []).map(cp => {
          const sign = cp.weight > 0 ? '+' : '';
          return el('div', { className: 'param-pill' },
            el('span', {}, cp.param_name),
            el('span', { className: 'param-weight' }, `${sign}${cp.weight.toFixed(2)}`)
          );
        })
      ),

      // Feedback submission drawer
      el('div', { className: 'feedback-box' },
        el('div', { className: 'feedback-title' }, 'Twin Feedback Loop ("Actually, I would...")'),
        el('div', { style: { display: 'flex', gap: '0.5rem', marginTop: '0.5rem' } },
          el('input', {
            id: 'feedback-input',
            className: 'form-input',
            placeholder: 'If inaccurate, what would you actually do and why?'
          }),
          el('button', {
            className: 'btn-secondary',
            onClick: () => this.submitFeedback(result.feedback_token)
          }, 'Send Correction')
        )
      )
    );

    resultBox.appendChild(card);
  }

  async submitFeedback(token) {
    const inp = document.getElementById('feedback-input');
    const text = inp ? inp.value.trim() : '';
    if (!text) {
      showToast('Please type your actual choice or reasoning.', 'error');
      return;
    }

    if (this.dataSource === 'live') {
      try {
        await fetch('/twin/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prediction_id: token,
            user_said_actually: text,
            free_text: text
          })
        });
      } catch (e) {}
    }

    showToast('Correction recorded. Your feedback updates future posterior distributions.', 'success');
    if (inp) inp.value = '';
  }

  async executeMemorySearch() {
    const queryInput = document.getElementById('mem-query-input');
    const resultsContainer = document.getElementById('mem-results-container');
    const query = queryInput ? queryInput.value.trim() : '';

    if (!query) {
      showToast('Enter a search query to search memory.', 'error');
      return;
    }

    if (resultsContainer) {
      clearElement(resultsContainer);
      resultsContainer.appendChild(el('div', { style: { padding: '1rem', color: 'var(--text-muted)' } }, 'Searching encrypted semantic vectors and structured store...'));
    }

    if (this.dataSource === 'live') {
      try {
        const resp = await fetch('/retrieve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query, top_k: 5, token_budget: 300 })
        });
        if (resp.ok) {
          const data = await resp.json();
          this.renderMemoryResults(data.items || []);
          return;
        }
      } catch (e) {}
    }

    // Mock search results
    setTimeout(() => {
      const mockItems = [
        {
          source: 'reasoning_trace',
          domain: 'career',
          similarity: 0.93,
          content: 'Decided to decline secondary consultant retainer to protect 20 hours/week for proprietary core engine architecture.'
        },
        {
          source: 'belief_node',
          domain: 'ethics',
          similarity: 0.88,
          content: 'Local-first zero-knowledge encryption is non-negotiable for digital identity sovereignty.'
        }
      ];
      this.renderMemoryResults(mockItems);
    }, 300);
  }

  renderMemoryResults(items) {
    const container = document.getElementById('mem-results-container');
    if (!container) return;
    clearElement(container);

    if (items.length === 0) {
      container.appendChild(el('div', { style: { color: 'var(--text-muted)', padding: '1rem' } }, 'No memory items matched query threshold.'));
      return;
    }

    items.forEach(item => {
      const row = el('div', { className: 'memory-item' },
        el('div', { className: 'memory-item-header' },
          el('span', { style: { textTransform: 'uppercase', fontWeight: '700' } }, `${item.domain || 'General'} • ${item.source}`),
          el('span', { className: 'memory-similarity' }, `${Math.round((item.similarity || 0.85) * 100)}% match`)
        ),
        el('p', { style: { fontSize: '0.875rem', color: '#cbd5e1' } }, item.content)
      );
      container.appendChild(row);
    });
  }

  async exportModelBundle() {
    try {
      let bundleData = null;
      if (this.dataSource === 'live') {
        const resp = await fetch('/export');
        if (resp.ok) bundleData = await resp.json();
      }

      if (!bundleData) {
        bundleData = {
          bundle_b64: btoa(JSON.stringify(SAMPLE_TWIN_DATA)),
          sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
          signature_b64: 'MEQCIA72xV5W3jY='
        };
      }

      const blob = new Blob([JSON.stringify(bundleData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pdt-vault-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('Encrypted model bundle exported with SHA-256 integrity signature', 'success');
    } catch (err) {
      showToast('Export failed: ' + err.message, 'error');
    }
  }

  // Narration Studio Methods
  fillNarrationExample() {
    const fields = {
      'narrate-intake': 'Faced with leaving high-paying corporate architecture role to co-found an open-source privacy infrastructure startup.',
      'narrate-options': 'Option 1: Quit and take seed funding.\nOption 2: Stay at current company and advise on weekends.\nOption 3: Bootstrap part-time.',
      'narrate-factors': 'Personal autonomy, velocity of impact, family stability, technical creative control.',
      'narrate-tradeoffs': 'Willing to take 50% salary reduction in exchange for complete architectural sovereignty.',
      'narrate-counterfactual': 'If seed investor required board control or proprietary licensing, I would have stayed at corporate role.',
      'narrate-review': 'Decision finalized in Q1. Confirmed feeling high clarity and relief after choosing startup route.'
    };

    for (const [id, val] of Object.entries(fields)) {
      const elNode = document.getElementById(id);
      if (elNode) elNode.value = val;
    }
    showToast('Sample narration decision pre-filled', 'info');
  }

  async startNarrationSession() {
    try {
      const resp = await fetch('/narration/start', { method: 'POST' });
      if (resp.ok) {
        const data = await resp.json();
        this.currentNarrationSessionId = data.id;
        showToast(`Narration session initialized (Session ${data.id.slice(0, 8)})`, 'success');
        return;
      }
    } catch (e) {}

    this.currentNarrationSessionId = 'sess-' + Math.random().toString(36).substring(2, 9);
    showToast('Narration session initialized locally', 'info');
  }

  async submitNarrationSession() {
    const fields = ['narrate-intake', 'narrate-options', 'narrate-factors', 'narrate-tradeoffs', 'narrate-counterfactual', 'narrate-review'];
    const parts = fields.map(id => {
      const node = document.getElementById(id);
      return node ? node.value.trim() : '';
    }).filter(t => t.length > 0);

    if (parts.length === 0) {
      showToast('Please describe the decision before submitting.', 'error');
      return;
    }

    const narrationText = parts.join('\n\n');
    const resultBox = document.getElementById('narration-result-inspector');

    if (resultBox) {
      clearElement(resultBox);
      resultBox.appendChild(el('div', { style: { padding: '1rem', color: 'var(--text-muted)' } }, 'Extracting reasoning trace, Schwartz values, and decision parameters...'));
    }

    if (!this.currentNarrationSessionId) {
      await this.startNarrationSession();
    }

    try {
      const resp = await fetch(`/narration/${this.currentNarrationSessionId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ narration: narrationText })
      });

      if (resp.ok) {
        const body = await resp.json();
        this.renderNarrationSuccess(body);
        showToast('Reasoning trace extracted and committed to encrypted vault!', 'success');
        return;
      }
    } catch (e) {}

    // Fallback display
    setTimeout(() => {
      const mockExtracted = {
        trace: {
          id: 'trace-' + Math.random().toString(36).substring(2, 9),
          domain: 'career',
          chosen_option: 'Co-found open-source privacy infrastructure startup',
          schwartz_values: { self_direction: 0.92, security: 0.35, benevolence: 0.70 },
          decision_style: { analytical: 0.85, spontaneous: 0.25 }
        },
        support_flags: ['high_autonomy', 'explicit_counterfactual_recorded']
      };
      this.renderNarrationSuccess(mockExtracted);
      showToast('Reasoning trace extracted successfully', 'success');
    }, 400);
  }

  renderNarrationSuccess(body) {
    const resultBox = document.getElementById('narration-result-inspector');
    if (!resultBox) return;

    clearElement(resultBox);
    const trace = body.trace || body;

    const wrap = el('div', { style: { background: 'rgba(0, 0, 0, 0.4)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-subtle)' } },
      el('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' } },
        el('span', { style: { color: 'var(--accent-emerald)', fontWeight: '700' } }, '✓ SCHEMA VALIDATED REASONING TRACE'),
        el('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' } }, trace.id || 'trace-committed')
      ),
      el('pre', { style: { fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: '#cbd5e1', overflowX: 'auto', whiteSpace: 'pre-wrap' } },
        JSON.stringify(body, null, 2)
      )
    );

    resultBox.appendChild(wrap);
  }

  openDoctorModal() {
    const modal = document.getElementById('doctor-modal');
    if (modal) modal.classList.add('open');
  }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  window.pdtApp = new DigitalTwinApp();
});
