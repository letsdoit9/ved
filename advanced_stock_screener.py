# Flexible Stock Screener - Choose Your Conditions
import pandas as pd
import numpy as np
import requests
import streamlit as st
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

# 🔧 AUTO-CONFIGURATION
AUTO_CONFIG = {
    "upstox_token": "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiJBSzg0NzUiLCJqdGkiOiI2ODQzZmFkMzI1NDU5YTJlZGZlMTkzNzMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc0OTI4NTU4NywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzQ5MzMzNjAwfQ.FIxAD2G4saQbG9MgKj7wBsswsDmVpcS5RLmUkUPiAQ4",
    "telegram_bot_token": "7923075723:AAGL5-DGPSU0TLb68vOLretVwioC6vK0fJk", 
    "telegram_chat_id": "457632002",
    "default_stocks": """instrument_key,tradingsymbol
NSE_EQ|NSE_EQ|INE585B01010,MARUTI
NSE_EQ|INE139A01034,NATIONALUM
NSE_EQ|INE763I01026,TARIL
NSE_EQ|INE970X01018,LEMONTREE
NSE_EQ|INE522D01027,MANAPPURAM
NSE_EQ|INE427F01016,CHALET
NSE_EQ|INE00R701025,DALBHARAT
NSE_EQ|INE917I01010,BAJAJ-AUTO
NSE_EQ|INE146L01010,KIRLOSENG
NSE_EQ|INE267A01025,HINDZINC
NSE_EQ|INE466L01038,360ONE
NSE_EQ|INE070A01015,SHREECEM
NSE_EQ|INE242C01024,ANANTRAJ
NSE_EQ|INE883F01010,AADHARHFC
NSE_EQ|INE749A01030,JINDALSTEL
NSE_EQ|INE171Z01026,BDL
NSE_EQ|INE591G01017,COFORGE
NSE_EQ|INE903U01023,SIGNATURE
NSE_EQ|INE160A01022,PNB
NSE_EQ|INE596F01018,PTCIL"""
}

class FlexibleScreener:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {AUTO_CONFIG["upstox_token"]}', 'Content-Type': 'application/json'})
    
    def get_data(self, instrument_key):
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
            url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
            response = self.session.get(url, timeout=10)
            data = response.json()
            if data.get('status') != 'success': return None
            candles = data.get('data', {}).get('candles', [])
            if not candles: return None
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            return df.sort_values('timestamp').reset_index(drop=True)
        except: return None
    
    def add_indicators(self, df):
        # EMAs & SMAs
        for period in [5, 13, 26]: df[f'ema{period}'] = df['close'].ewm(span=period).mean()
        for period in [20, 50, 100, 200]: df[f'sma{period}'] = df['close'].rolling(period).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + gain / loss.replace(0, np.inf)))
        
        # Stochastic RSI
        rsi_min = df['rsi'].rolling(14).min()
        rsi_max = df['rsi'].rolling(14).max()
        df['stoch_rsi'] = ((df['rsi'] - rsi_min) / (rsi_max - rsi_min)) * 100
        
        # ADX & DI
        high, low, close = df['high'], df['low'], df['close']
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        plus_dm = high.diff().where((high.diff() > low.diff()) & (high.diff() > 0), 0)
        minus_dm = abs(low.diff()).where((low.diff() > high.diff()) & (low.diff() < 0), 0)
        atr = tr.rolling(10).mean()
        df['plus_di'] = 100 * (plus_dm.rolling(10).mean() / atr)
        df['minus_di'] = 100 * (minus_dm.rolling(10).mean() / atr)
        
        # MACD
        ema14 = df['close'].ewm(span=14).mean()
        ema5 = df['close'].ewm(span=5).mean()
        df['macd_line'] = ema14 - ema5
        df['macd_signal'] = df['macd_line'].ewm(span=3).mean()
        
        # Bollinger Bands
        sma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        df['bb_upper'] = sma20 + (std20 * 2)
        
        # Volume & Price
        df['vol_50ma'] = df['volume'].rolling(50).mean()
        df['high_300d'] = df['high'].rolling(300, min_periods=1).max()
        df['prev_close'] = df['close'].shift(1)
        
        return df
    
    def check_conditions(self, df, symbol, selected_conditions):
        if len(df) < 300: return None
        df = self.add_indicators(df)
        latest = df.iloc[-1]
        
        all_conditions = {
            '5 EMA > 20 SMA': latest['ema5'] > latest['sma20'],
            '13 EMA > 20 SMA': latest['ema13'] > latest['sma20'], 
            '26 EMA > 20 SMA': latest['ema26'] > latest['sma20'],
            '50 SMA > 20 SMA': latest['sma50'] > latest['sma20'],
            '100 SMA > 20 SMA': latest['sma100'] > latest['sma20'],
            '200 SMA > 20 SMA': latest['sma200'] > latest['sma20'],
            'ADX +DI ≥ -DI': latest['plus_di'] >= latest['minus_di'],
            'MACD Line ≥ Signal': latest['macd_line'] >= latest['macd_signal'],
            'RSI > 40': latest['rsi'] > 40,
            'Stoch RSI > 30': latest['stoch_rsi'] > 30,
            'Close ≥ Upper BB': latest['close'] >= latest['bb_upper'],
            'Bullish Candle': latest['close'] > latest['open'],
            'Volume > 100K': latest['volume'] > 100000,
            'Close × 1.05 > 300d High': latest['close'] * 1.05 > latest['high_300d'],
            'Close > Yesterday': latest['close'] > latest['prev_close'],
            'Volume > 50d Avg': latest['volume'] > latest['vol_50ma']
        }
        
        # Check only selected conditions
        selected_results = {k: v for k, v in all_conditions.items() if k in selected_conditions}
        conditions_met = sum(selected_results.values())
        
        if conditions_met == len(selected_conditions):  # All selected conditions met
            atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
            return {
                'Stock': symbol,
                'Entry': f"₹{latest['close']:.2f}",
                'Stop Loss': f"₹{latest['close'] - atr * 2:.2f}",
                'Target': f"₹{latest['close'] + atr * 3:.2f}",
                'RSI': f"{latest['rsi']:.1f}",
                'Volume Ratio': f"{latest['volume']/latest['vol_50ma']:.2f}x",
                'Conditions': f"{conditions_met}/{len(selected_conditions)}"
            }
        return None
    
    def scan_stocks(self, stock_list, selected_conditions):
        signals = []
        progress = st.progress(0)
        
        def analyze_stock(stock_data):
            instrument_key, symbol = stock_data
            df = self.get_data(instrument_key)
            return self.check_conditions(df, symbol, selected_conditions) if df is not None else None
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(analyze_stock, stock) for stock in stock_list]
            for i, future in enumerate(futures):
                try:
                    result = future.result()
                    if result: 
                        signals.append(result)
                        st.success(f"✅ {result['Stock']}")
                except: pass
                progress.progress((i + 1) / len(stock_list))
        return signals
    
    def send_telegram(self, signals, conditions_count):
        if not AUTO_CONFIG["telegram_bot_token"]: return False
        message = f"📈 {len(signals)} Stocks Found ({conditions_count} conditions):\n\n" if signals else "📈 No signals found"
        if signals:
            for i, s in enumerate(signals, 1):
                message += f"{i}. {s['Stock']}\nEntry: {s['Entry']} | SL: {s['Stop Loss']} | Target: {s['Target']}\nRSI: {s['RSI']} | Vol: {s['Volume Ratio']}\n\n"
        try:
            requests.post(f"https://api.telegram.org/bot{AUTO_CONFIG['telegram_bot_token']}/sendMessage", 
                         data={"chat_id": AUTO_CONFIG["telegram_chat_id"], "text": message})
            return True
        except: return False

def main():
    st.set_page_config(page_title="Flexible Stock Screener", layout="wide")
    st.title("🎯 Flexible Stock Screener")
    
    # Condition Selection
    st.sidebar.header("📊 Select Conditions")
    all_conditions = [
        '5 EMA > 20 SMA', '13 EMA > 20 SMA', '26 EMA > 20 SMA',
        '50 SMA > 20 SMA', '100 SMA > 20 SMA', '200 SMA > 20 SMA',
        'ADX +DI ≥ -DI', 'MACD Line ≥ Signal', 'RSI > 40', 'Stoch RSI > 30',
        'Close ≥ Upper BB', 'Bullish Candle', 'Volume > 100K',
        'Close × 1.05 > 300d High', 'Close > Yesterday', 'Volume > 50d Avg'
    ]
    
    # Quick presets
    preset = st.sidebar.selectbox("🚀 Quick Presets:", 
        ["Custom", "Basic Trend (6)", "Advanced Momentum (10)", "All Conditions (16)"])
    
    if preset == "Basic Trend (6)":
        default_conditions = ['5 EMA > 20 SMA', '13 EMA > 20 SMA', 'RSI > 40', 'Bullish Candle', 'Volume > 100K', 'Close > Yesterday']
    elif preset == "Advanced Momentum (10)":
        default_conditions = ['5 EMA > 20 SMA', '13 EMA > 20 SMA', '26 EMA > 20 SMA', 'MACD Line ≥ Signal', 'RSI > 40', 
                             'Stoch RSI > 30', 'Bullish Candle', 'Volume > 100K', 'Close > Yesterday', 'Volume > 50d Avg']
    elif preset == "All Conditions (16)":
        default_conditions = all_conditions
    else:
        default_conditions = ['5 EMA > 20 SMA', '13 EMA > 20 SMA', 'RSI > 40', 'Bullish Candle']
    
    selected_conditions = st.sidebar.multiselect("Choose Conditions:", all_conditions, default=default_conditions)
    
    st.sidebar.success(f"✅ {len(selected_conditions)} conditions selected")
    
    # Stock upload
    uploaded_file = st.file_uploader("📁 Upload CSV (optional)", type=['csv'])
    csv_content = uploaded_file.getvalue().decode('utf-8') if uploaded_file else AUTO_CONFIG["default_stocks"]
    
    if not uploaded_file:
        st.info("📊 Using default 20 stocks")
    
    # Parse stocks
    try:
        df = pd.read_csv(StringIO(csv_content))
        stock_list = [(row['instrument_key'], row['tradingsymbol']) for _, row in df.iterrows()]
    except:
        st.error("❌ Invalid CSV format")
        return
    
    # Display selected conditions
    if selected_conditions:
        st.info(f"🎯 **Selected {len(selected_conditions)} Conditions:** " + " • ".join(selected_conditions))
    else:
        st.warning("⚠️ Please select at least one condition")
        return
    
    # Scan button
    if st.button("🔍 START FLEXIBLE SCAN", type="primary", use_container_width=True):
        screener = FlexibleScreener()
        
        with st.spinner(f"Scanning {len(stock_list)} stocks with {len(selected_conditions)} conditions..."):
            signals = screener.scan_stocks(stock_list, selected_conditions)
        
        if signals:
            st.success(f"🎯 Found {len(signals)} stocks meeting {len(selected_conditions)} conditions!")
            df_results = pd.DataFrame(signals)
            st.dataframe(df_results, use_container_width=True)
            
            csv_data = df_results.to_csv(index=False)
            st.download_button("📥 Download Results", csv_data, f"flexible_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
            
            if screener.send_telegram(signals, len(selected_conditions)):
                st.success("📱 Sent to Telegram!")
        else:
            st.warning(f"😔 No stocks found meeting {len(selected_conditions)} selected conditions")
            st.info("💡 Try reducing the number of conditions or selecting different ones")

if __name__ == "__main__":
    main()