/* App bootstrap: wires the toolbar, loads market data, and coordinates the
 * ChartManager, Indicators and Backtest modules. Exposes shared state on
 * window.CS. */
(function () {
  const CS = {
    source: 'binance',
    symbol: 'BTCUSDT',
    interval: '1h',
    candles: [],
    sources: [],
    intervals: [],

    removeIndicator(key) { Indicators.remove(key); },

    toast(msg, kind) {
      const el = document.getElementById('toast');
      el.textContent = msg;
      el.className = 'toast ' + (kind || '');
      clearTimeout(this._toastT);
      this._toastT = setTimeout(() => el.classList.add('hidden'), 3200);
    },
  };
  window.CS = CS;

  function setStatus(state) {
    const dot = document.getElementById('statusDot');
    dot.className = 'status-dot ' + (state || '');
  }

  function setLoading(on) {
    document.getElementById('loading').classList.toggle('hidden', !on);
  }

  async function loadSources() {
    const res = await fetch('./api/sources');
    const data = await res.json();
    CS.sources = data.sources;
    CS.intervals = data.intervals;

    const sel = document.getElementById('sourceSelect');
    sel.innerHTML = '';
    data.sources.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id; opt.textContent = s.label;
      sel.appendChild(opt);
    });
    sel.value = CS.source;
    sel.addEventListener('change', () => {
      CS.source = sel.value;
      updateSymbolSuggestions();
    });

    // intervals
    const grp = document.getElementById('intervalGroup');
    grp.innerHTML = '';
    data.intervals.forEach(iv => {
      const b = document.createElement('button');
      b.textContent = iv;
      b.dataset.iv = iv;
      if (iv === CS.interval) b.classList.add('active');
      b.addEventListener('click', () => {
        CS.interval = iv;
        grp.querySelectorAll('button').forEach(x => x.classList.toggle('active', x.dataset.iv === iv));
        loadData();
      });
      grp.appendChild(b);
    });

    updateSymbolSuggestions();
  }

  function updateSymbolSuggestions() {
    const src = CS.sources.find(s => s.id === CS.source);
    const list = document.getElementById('symbolList');
    list.innerHTML = '';
    (src ? src.examples : []).forEach(ex => {
      const o = document.createElement('option');
      o.value = ex;
      list.appendChild(o);
    });
    const input = document.getElementById('symbolInput');
    if (src && src.hint) input.title = src.hint;
  }

  async function loadData() {
    const symbol = document.getElementById('symbolInput').value.trim() || CS.symbol;
    CS.symbol = symbol;
    setLoading(true);
    setStatus('busy');
    try {
      const url = `./api/ohlcv?source=${encodeURIComponent(CS.source)}` +
                  `&symbol=${encodeURIComponent(symbol)}&interval=${CS.interval}&limit=1000`;
      const res = await fetch(url);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'โหลดข้อมูลไม่สำเร็จ');
      }
      const data = await res.json();
      CS.candles = data.candles;
      ChartManager.setCandles(CS.candles);
      document.getElementById('chartTitle').textContent = `${symbol} · ${CS.interval}`;
      await Indicators.recomputeAll();
      Backtest.clear();
      setStatus('ok');
    } catch (e) {
      setStatus('err');
      CS.toast(e.message, 'err');
    } finally {
      setLoading(false);
    }
  }

  function bindMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('backdrop');
    const toggle = () => {
      const open = sidebar.classList.toggle('open');
      backdrop.classList.toggle('show', open);
    };
    document.getElementById('menuToggle').addEventListener('click', toggle);
    backdrop.addEventListener('click', toggle);
  }

  async function init() {
    ChartManager.init(document.getElementById('mainChart'));
    bindMobileSidebar();

    document.getElementById('loadBtn').addEventListener('click', loadData);
    document.getElementById('symbolInput').addEventListener('keydown', e => {
      if (e.key === 'Enter') loadData();
    });
    document.getElementById('symbolInput').value = CS.symbol;

    try {
      await loadSources();
      await Indicators.load();
      await Backtest.load();
      await loadData();
    } catch (e) {
      CS.toast('เริ่มต้นแอปไม่สำเร็จ: ' + e.message, 'err');
      setStatus('err');
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
