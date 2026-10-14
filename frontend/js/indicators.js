/* Indicator catalog UI: browse/add indicators, edit params, render via the
 * ChartManager, and keep an "active indicators" list in the sidebar. */
(function () {
  const Indicators = {
    catalog: [],         // meta from /api/indicators
    active: {},          // key -> { id, name, overlay, params }
    _settingsKey: null,

    async load() {
      const res = await fetch('./api/indicators');
      const data = await res.json();
      this.catalog = data.indicators || [];
      this._renderCatalog();
      this._bindModals();
      this.renderActive();
    },

    byId(id) { return this.catalog.find(c => c.id === id); },

    _renderCatalog(filter = '') {
      const grid = document.getElementById('indicatorCatalog');
      const f = filter.trim().toLowerCase();
      grid.innerHTML = '';
      this.catalog
        .filter(c => !f || c.name.toLowerCase().includes(f) || c.id.includes(f))
        .forEach(c => {
          const div = document.createElement('div');
          div.className = 'cat-item';
          div.innerHTML = `<div class="cat-name">${c.name}</div><div class="cat-group">${c.group}</div>`;
          div.addEventListener('click', () => { this.add(c.id); this._closeModal('indicatorModal'); });
          grid.appendChild(div);
        });
    },

    _defaultParams(meta) {
      const p = {};
      (meta.params || []).forEach(pp => { p[pp.key] = pp.default; });
      return p;
    },

    /* key allows multiple of the same indicator (e.g. two SMAs) */
    add(id, params) {
      const meta = this.byId(id);
      if (!meta) return;
      const key = `${id}_${Date.now().toString(36)}`;
      this.active[key] = {
        id, name: meta.name, overlay: meta.overlay,
        params: params || this._defaultParams(meta),
      };
      this.renderActive();
      this._computeOne(key);
    },

    remove(key) {
      if (!this.active[key]) return;
      if (this.active[key].overlay) ChartManager.removeOverlay(key);
      else ChartManager.removePane(key);
      delete this.active[key];
      this.renderActive();
    },

    /* recompute everything (e.g. after loading new candles) */
    async recomputeAll() {
      for (const key of Object.keys(this.active)) await this._computeOne(key);
    },

    async _computeOne(key) {
      const item = this.active[key];
      const candles = window.CS.candles;
      if (!item || !candles || !candles.length) return;
      try {
        const res = await fetch('./api/indicators/compute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ohlcv: candles, indicators: [{ id: item.id, params: item.params }] }),
        });
        const data = await res.json();
        const result = (data.results || [])[0];
        if (!result || result.error) { window.CS.toast(`คำนวณ ${item.name} ไม่สำเร็จ`, 'err'); return; }
        if (result.overlay) ChartManager.addOverlay(key, result.plots);
        else ChartManager.addPane(key, result.name, result.plots);
        // capture primary color for the sidebar swatch
        item.color = (result.plots[0] || {}).color || '#2962ff';
        this.renderActive();
      } catch (e) {
        window.CS.toast('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้', 'err');
      }
    },

    renderActive() {
      const ul = document.getElementById('activeIndicators');
      ul.innerHTML = '';
      const keys = Object.keys(this.active);
      if (!keys.length) {
        ul.innerHTML = '<li class="empty">ยังไม่มี indicator — กด "+ เพิ่ม"</li>';
        return;
      }
      keys.forEach(key => {
        const item = this.active[key];
        const li = document.createElement('li');
        const label = this._label(item);
        li.innerHTML =
          `<span class="swatch" style="background:${item.color || '#2962ff'}"></span>` +
          `<span class="name" title="${label}">${label}</span>` +
          `<button class="row-btn" data-act="edit" title="ตั้งค่า">⚙</button>` +
          `<button class="row-btn" data-act="del" title="ลบ">✕</button>`;
        li.querySelector('[data-act="edit"]').addEventListener('click', () => this._openSettings(key));
        li.querySelector('[data-act="del"]').addEventListener('click', () => this.remove(key));
        ul.appendChild(li);
      });
    },

    _label(item) {
      const nums = Object.entries(item.params)
        .filter(([k]) => k !== 'color')
        .map(([, v]) => v).join(', ');
      return nums ? `${item.name} (${nums})` : item.name;
    },

    /* ---------- settings modal ---------- */
    _openSettings(key) {
      const item = this.active[key];
      const meta = this.byId(item.id);
      this._settingsKey = key;
      document.getElementById('settingsTitle').textContent = `ตั้งค่า: ${item.name}`;
      const box = document.getElementById('settingsParams');
      box.innerHTML = '';
      (meta.params || []).forEach(p => {
        const field = document.createElement('label');
        field.className = 'field';
        const type = p.type === 'color' ? 'color' : 'number';
        const val = item.params[p.key] ?? p.default;
        field.innerHTML = `<span>${p.label}</span>` +
          `<input class="tb-input full" type="${type}" step="any" data-key="${p.key}" value="${val}">`;
        box.appendChild(field);
      });
      if (!(meta.params || []).length) box.innerHTML = '<p class="hint">indicator นี้ไม่มีพารามิเตอร์</p>';
      document.getElementById('settingsModal').classList.remove('hidden');
    },

    _applySettings() {
      const key = this._settingsKey;
      if (!key || !this.active[key]) return;
      const inputs = document.querySelectorAll('#settingsParams input');
      inputs.forEach(inp => {
        const k = inp.dataset.key;
        this.active[key].params[k] = inp.type === 'color' ? inp.value : parseFloat(inp.value);
      });
      this._closeModal('settingsModal');
      this._computeOne(key);
    },

    _bindModals() {
      document.getElementById('addIndicatorBtn').addEventListener('click', () => {
        this._renderCatalog();
        document.getElementById('indicatorModal').classList.remove('hidden');
      });
      document.getElementById('closeModal').addEventListener('click', () => this._closeModal('indicatorModal'));
      document.getElementById('closeSettings').addEventListener('click', () => this._closeModal('settingsModal'));
      document.getElementById('applySettings').addEventListener('click', () => this._applySettings());
      document.getElementById('indicatorSearch').addEventListener('input', e => this._renderCatalog(e.target.value));
      // click backdrop to close
      ['indicatorModal', 'settingsModal'].forEach(id => {
        document.getElementById(id).addEventListener('click', e => {
          if (e.target.id === id) this._closeModal(id);
        });
      });
    },

    _closeModal(id) { document.getElementById(id).classList.add('hidden'); },
  };

  window.Indicators = Indicators;
})();
