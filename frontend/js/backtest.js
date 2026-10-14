/* Backtest UI: choose a preset strategy + params, run it on the server, and
 * render stats, an equity-curve pane and entry/exit markers on the price chart. */
(function () {
  const Backtest = {
    strategies: [],
    _equityKey: '__equity__',

    async load() {
      const res = await fetch('./api/strategies');
      const data = await res.json();
      this.strategies = data.strategies || [];
      const sel = document.getElementById('strategySelect');
      sel.innerHTML = '';
      this.strategies.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id; opt.textContent = s.name;
        sel.appendChild(opt);
      });
      sel.addEventListener('change', () => this._renderParams());
      document.getElementById('runBacktestBtn').addEventListener('click', () => this.run());
      this._renderParams();
    },

    _current() {
      const id = document.getElementById('strategySelect').value;
      return this.strategies.find(s => s.id === id);
    },

    _renderParams() {
      const strat = this._current();
      document.getElementById('strategyDesc').textContent = strat ? strat.desc : '';
      const box = document.getElementById('strategyParams');
      box.innerHTML = '';
      (strat ? strat.params : []).forEach(p => {
        const field = document.createElement('label');
        field.className = 'field';
        field.innerHTML = `<span>${p.label}</span>` +
          `<input class="tb-input full" type="number" step="any" data-key="${p.key}" value="${p.default}">`;
        box.appendChild(field);
      });
    },

    _collectParams() {
      const params = {};
      document.querySelectorAll('#strategyParams input').forEach(inp => {
        params[inp.dataset.key] = parseFloat(inp.value);
      });
      return params;
    },

    async run() {
      const strat = this._current();
      if (!strat || !window.CS.symbol) { window.CS.toast('เลือกสัญลักษณ์ก่อน', 'err'); return; }
      const btn = document.getElementById('runBacktestBtn');
      btn.disabled = true; btn.textContent = 'กำลังรัน...';
      try {
        const res = await fetch('./api/backtest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source: window.CS.source,
            symbol: window.CS.symbol,
            interval: window.CS.interval,
            strategy: strat.id,
            params: this._collectParams(),
            limit: 1000,
            initial_cash: parseFloat(document.getElementById('initialCash').value) || 10000,
            commission: parseFloat(document.getElementById('commission').value) || 0,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'backtest ล้มเหลว');
        }
        const data = await res.json();
        this._renderResult(data);
        ChartManager.setMarkers(data.markers);
        this._renderEquity(data.equity_curve);
        window.CS.toast('Backtest เสร็จแล้ว', 'ok');
      } catch (e) {
        window.CS.toast(e.message, 'err');
      } finally {
        btn.disabled = false; btn.textContent = '▶ รัน Backtest';
      }
    },

    _renderResult(data) {
      const s = data.stats;
      const cls = v => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
      const box = document.getElementById('backtestResult');
      box.innerHTML = `
        <div class="stat-grid">
          <div class="stat"><div class="label">ผลตอบแทน</div><div class="value ${cls(s.total_return_pct)}">${s.total_return_pct}%</div></div>
          <div class="stat"><div class="label">Buy & Hold</div><div class="value ${cls(s.buy_hold_return_pct)}">${s.buy_hold_return_pct}%</div></div>
          <div class="stat"><div class="label">Max DD</div><div class="value neg">${s.max_drawdown_pct}%</div></div>
          <div class="stat"><div class="label">Win rate</div><div class="value">${s.win_rate_pct}%</div></div>
          <div class="stat"><div class="label">จำนวนเทรด</div><div class="value">${s.num_trades}</div></div>
          <div class="stat"><div class="label">Sharpe</div><div class="value ${cls(s.sharpe)}">${s.sharpe}</div></div>
        </div>
        <p class="hint" style="margin-top:8px">ทุนปลายทาง: ${s.final_equity.toLocaleString()} (เริ่ม ${s.initial_cash.toLocaleString()})</p>`;
    },

    _renderEquity(curve) {
      if (!curve || !curve.length) return;
      ChartManager.addPane(this._equityKey, 'Equity Curve',
        [{ key: 'equity', type: 'line', color: '#f0b90b', data: curve }]);
    },

    clear() {
      ChartManager.clearMarkers();
      ChartManager.removePane(this._equityKey);
      document.getElementById('backtestResult').innerHTML = '';
    },
  };

  window.Backtest = Backtest;
})();
