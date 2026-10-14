# 📈 Chart Studio — เว็บแอปวิเคราะห์กราฟ + Backtest

เว็บแอป responsive สำหรับดูและวิเคราะห์กราฟราคาแบบ TradingView ใช้ได้ทั้งคอมและมือถือ
รองรับ **คริปโต (Binance), หุ้นไทย/สากล, ทองคำ และ Forex** พร้อม indicator ชุดหลักครบ
และระบบ **backtest ย้อนหลัง**

> หมายเหตุ: TradingView เป็นซอฟต์แวร์ proprietary จึงไม่สามารถ "ใช้ indicator ทุกตัวของ TradingView"
> แบบ 1:1 ได้ แอปนี้ใช้ไลบรารีโอเพนซอร์ส (`ta`) ซึ่งมี indicator หลักครบถ้วน และแสดงผลด้วย
> [TradingView Lightweight Charts™](https://github.com/tradingview/lightweight-charts) (ฟรี/โอเพนซอร์ส)

## คุณสมบัติ
- 📊 กราฟแท่งเทียน + ปริมาณ (candlestick + volume) ลื่นไหล ซูม/แพนได้ รองรับทัช
- 🧮 Indicator กว่า 20 ตัว: SMA, EMA, WMA, VWAP, Bollinger, Keltner, Donchian, Ichimoku, Parabolic SAR,
  RSI, MACD, Stochastic, Stoch RSI, ATR, ADX/DMI, CCI, Williams %R, ROC, MFI, OBV, Awesome Oscillator
  — overlay บนกราฟหลัก หรือแยก pane ด้านล่าง ปรับพารามิเตอร์/สีได้
- ⏱️ หลาย timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
- 🔁 Backtest 4 กลยุทธ์สำเร็จรูป (MA Crossover, RSI Reversion, MACD Cross, Bollinger Breakout)
  พร้อมสถิติ (ผลตอบแทน, Buy&Hold, Max Drawdown, Win rate, Sharpe), equity curve และจุดซื้อ/ขายบนกราฟ
- 📱 Responsive: บนมือถือ sidebar ยุบเป็น drawer

## โครงสร้าง
```
backend/
  main.py          FastAPI app + routes + serve frontend
  data_sources.py  Binance + Yahoo Finance -> OHLCV มาตรฐานเดียว
  indicators.py    catalog + การคำนวณ (ไลบรารี ta)
  backtest.py      เอนจิน backtest + กลยุทธ์ preset
frontend/
  index.html, css/styles.css, js/*.js   (Lightweight Charts v4)
```

## วิธีรัน
```bash
cd backend
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --port 8000
```
เปิดเบราว์เซอร์ที่ <http://localhost:8000>

## ตัวอย่างสัญลักษณ์
| ตลาด | ตัวอย่าง |
|------|----------|
| คริปโต (Binance) | `BTCUSDT`, `ETHUSDT`, `SOLUSDT` |
| หุ้นสากล | `AAPL`, `MSFT`, `TSLA` |
| หุ้นไทย | `PTT.BK`, `KBANK.BK`, `CPALL.BK` |
| ทองคำ | `GC=F`, `XAUUSD=X` |
| Forex | `EURUSD=X`, `USDTHB=X`, `JPY=X` |

## API หลัก
- `GET  /api/sources` — แหล่งข้อมูล + timeframe
- `GET  /api/ohlcv?source=&symbol=&interval=&limit=` — แท่งเทียน OHLCV
- `GET  /api/indicators` — catalog indicator
- `POST /api/indicators/compute` — คำนวณ indicator จาก OHLCV
- `GET  /api/strategies` — รายการกลยุทธ์ backtest
- `POST /api/backtest` — รัน backtest

เอกสาร API อัตโนมัติที่ `/docs`

## ข้อจำกัด
- ข้อมูล Yahoo Finance มี rate-limit และดีเลย์ (ไม่ใช่ real-time); 4h ใช้การ resample จาก 1h
- Backtest เป็นแบบ long/flat (ไม่มี short/leverage) เพื่อให้เข้าใจง่ายและตรวจสอบได้
- ใช้เพื่อการศึกษา/วิเคราะห์เท่านั้น ไม่ใช่คำแนะนำการลงทุน
