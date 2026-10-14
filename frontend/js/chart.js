/* Chart manager: main price chart (candles + volume) plus synced oscillator
 * panes rendered as separate Lightweight-Charts instances stacked below, with
 * their time scales kept in sync. */
(function () {
  const LWC = window.LightweightCharts;

  const CHART_OPTS = {
    layout: { background: { type: 'solid', color: '#131722' }, textColor: '#d1d4dc', fontSize: 11 },
    grid: { vertLines: { color: '#1e2433' }, horzLines: { color: '#1e2433' } },
    rightPriceScale: { borderColor: '#2a3245' },
    timeScale: { borderColor: '#2a3245', timeVisible: true, secondsVisible: false },
    crosshair: { mode: LWC.CrosshairMode.Normal },
    autoSize: true,
  };

  const CANDLE_OPTS = {
    upColor: '#26a69a', downColor: '#ef5350',
    borderUpColor: '#26a69a', borderDownColor: '#ef5350',
    wickUpColor: '#26a69a', wickDownColor: '#ef5350',
  };

  const ChartManager = {
    main: null,
    candle: null,
    volume: null,
    overlays: {},      // indicatorKey -> [series]
    panes: {},         // indicatorKey -> { el, chart, series:[] }
    _syncing: false,
    _candleData: [],

    init(container) {
      this.main = LWC.createChart(container, CHART_OPTS);
      this.candle = this.main.addCandlestickSeries(CANDLE_OPTS);
      this.volume = this.main.addHistogramSeries({
        priceScaleId: 'vol',
        priceFormat: { type: 'volume' },
        color: '#3a4a63',
      });
      this.main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      this._syncTimeScale(this.main);
      this._bindLegend();
      window.addEventListener('resize', () => this._resizePanes());
    },

    setCandles(candles) {
      this._candleData = candles;
      this.candle.setData(candles.map(c => ({
        time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
      })));
      this.volume.setData(candles.map(c => ({
        time: c.time, value: c.volume,
        color: c.close >= c.open ? 'rgba(38,166,154,.45)' : 'rgba(239,83,80,.45)',
      })));
      this.main.timeScale().fitContent();
    },

    /* ---------- overlays (on main chart) ---------- */
    addOverlay(key, plots) {
      this.removeOverlay(key);
      const series = [];
      plots.forEach(plot => {
        const s = this.main.addLineSeries({
          color: plot.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
        });
        s.setData(plot.data);
        series.push(s);
      });
      this.overlays[key] = series;
    },

    removeOverlay(key) {
      (this.overlays[key] || []).forEach(s => this.main.removeSeries(s));
      delete this.overlays[key];
    },

    /* ---------- oscillator panes ---------- */
    addPane(key, name, plots) {
      this.removePane(key);
      const wrap = document.getElementById('panes');
      const el = document.createElement('div');
      el.className = 'osc-pane';
      el.style.height = '140px';
      el.innerHTML = `<span class="osc-label">${name}</span>` +
                     `<button class="osc-close" data-key="${key}">✕</button>`;
      wrap.appendChild(el);

      const chart = LWC.createChart(el, {
        ...CHART_OPTS,
        timeScale: { ...CHART_OPTS.timeScale, visible: false },
      });

      const series = [];
      plots.forEach(plot => {
        let s;
        if (plot.type === 'histogram') {
          s = chart.addHistogramSeries({ color: plot.color, priceLineVisible: false });
          s.setData(plot.data.map(d => ({
            time: d.time, value: d.value,
            color: d.value >= 0 ? 'rgba(38,166,154,.8)' : 'rgba(239,83,80,.8)',
          })));
        } else {
          s = chart.addLineSeries({ color: plot.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
          s.setData(plot.data);
        }
        // reference level lines (e.g. RSI 30/70)
        (plot.levels || []).forEach(lv => {
          s.createPriceLine({ price: lv, color: '#3a4a63', lineWidth: 1, lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: false });
        });
        series.push(s);
      });

      el.querySelector('.osc-close').addEventListener('click', e => {
        const k = e.currentTarget.dataset.key;
        if (window.CS && window.CS.removeIndicator) window.CS.removeIndicator(k);
      });

      this.panes[key] = { el, chart, series };
      this._syncTimeScale(chart);
      this._applyMainRangeTo(chart);
      this._resizePanes();
    },

    removePane(key) {
      const pane = this.panes[key];
      if (!pane) return;
      pane.chart.remove();
      pane.el.remove();
      delete this.panes[key];
      this._resizePanes();
    },

    hasIndicator(key) {
      return !!this.overlays[key] || !!this.panes[key];
    },

    clearIndicators() {
      Object.keys(this.overlays).forEach(k => this.removeOverlay(k));
      Object.keys(this.panes).forEach(k => this.removePane(k));
    },

    /* ---------- backtest ---------- */
    setMarkers(markers) {
      this.candle.setMarkers(markers || []);
    },
    clearMarkers() {
      this.candle.setMarkers([]);
    },

    /* ---------- internals ---------- */
    _allCharts() {
      return [this.main, ...Object.values(this.panes).map(p => p.chart)];
    },

    _syncTimeScale(chart) {
      chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (this._syncing || !range) return;
        this._syncing = true;
        this._allCharts().forEach(c => {
          if (c !== chart) c.timeScale().setVisibleLogicalRange(range);
        });
        this._syncing = false;
      });
    },

    _applyMainRangeTo(chart) {
      const range = this.main.timeScale().getVisibleLogicalRange();
      if (range) chart.timeScale().setVisibleLogicalRange(range);
    },

    _resizePanes() {
      // panes use autoSize; nothing manual needed, but keep hook for future.
    },

    _bindLegend() {
      const legend = document.getElementById('ohlcLegend');
      this.main.subscribeCrosshairMove(param => {
        if (!param.time || !param.seriesData || !this.candle) { legend.innerHTML = ''; return; }
        const bar = param.seriesData.get(this.candle);
        if (!bar) { legend.innerHTML = ''; return; }
        const col = bar.close >= bar.open ? '#26a69a' : '#ef5350';
        legend.innerHTML =
          `O <b>${fmt(bar.open)}</b> H <b>${fmt(bar.high)}</b> ` +
          `L <b>${fmt(bar.low)}</b> C <b style="color:${col}">${fmt(bar.close)}</b>`;
      });
    },
  };

  function fmt(v) {
    if (v == null) return '-';
    const abs = Math.abs(v);
    const dp = abs >= 1000 ? 2 : abs >= 1 ? 2 : 4;
    return v.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }

  window.ChartManager = ChartManager;
})();
