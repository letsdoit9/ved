# Advanced Automated Stock Screener - Multiple Filter Version
import pandas as pd
import numpy as np
import requests
import streamlit as st
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

# 🔧 AUTO-CONFIGURATION - Edit these values once
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

class AdvancedStockScreener:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {AUTO_CONFIG["upstox_token"]}',
            'Content-Type': 'application/json'
        })
    
    def get_data(self, instrument_key):
        """Get stock data - extended to 400 days for 300-day high calculation"""
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
            url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
            
            response = self.session.get(url, timeout=10)
            data = response.json()
            
            if data.get('status') != 'success':
                return None
                
            candles = data.get('data', {}).get('candles', [])
            if not candles:
                return None
                
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df.sort_values('timestamp').reset_index(drop=True)
            
        except Exception as e:
            return None
    
    def calculate_indicators(self, df):
        """Calculate all required indicators"""
        # EMAs and SMAs
        df['ema5'] = df['close'].ewm(span=5).mean()
        df['ema13'] = df['close'].ewm(span=13).mean()
        df['ema26'] = df['close'].ewm(span=26).mean()
        df['sma20'] = df['close'].rolling(20).mean()
        df['sma50'] = df['close'].rolling(50).mean()
        df['sma100'] = df['close'].rolling(100).mean()
        df['sma200'] = df['close'].rolling(200).mean()
        
        # Technical indicators
        df['rsi'] = self.rsi(df['close'], 14)
        df['stoch_rsi'] = self.stochastic_rsi(df['close'], 14)
        df = self.add_adx(df, 10)
        df = self.add_macd(df, 14, 5, 3)
        df = self.add_bollinger_bands(df, 20, 2)
        
        # Volume indicators
        df['vol_50ma'] = df['volume'].rolling(50).mean()
        df['vol_ratio'] = df['volume'] / df['vol_50ma']
        
        # Price comparisons
        df['high_300d'] = df['high'].rolling(300, min_periods=1).max()
        df['prev_close'] = df['close'].shift(1)
        
        return df
    
    def rsi(self, prices, period=14):
        """RSI calculation"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = -delta.where(delta < 0, 0).rolling(period).mean()
        rs = gain / loss.replace(0, np.inf)
        return 100 - (100 / (1 + rs))
    
    def stochastic_rsi(self, prices, period=14):
        """Stochastic RSI calculation"""
        rsi = self.rsi(prices, period)
        stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min()) * 100
        return stoch_rsi
    
    def add_adx(self, df, period=10):
        """Add ADX, +DI, -DI indicators"""
        high, low, close = df['high'], df['low'], df['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        minus_dm = abs(minus_dm)
        
        # Smoothed values
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di
        df['adx'] = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
        
        return df
    
    def add_macd(self, df, fast=14, slow=5, signal=3):
        """Add MACD indicators"""
        ema_fast = df['close'].ewm(span=fast).mean()
        ema_slow = df['close'].ewm(span=slow).mean()
        df['macd_line'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd_line'].ewm(span=signal).mean()
        df['macd_histogram'] = df['macd_line'] - df['macd_signal']
        return df
    
    def add_bollinger_bands(self, df, period=20, std_dev=2):
        """Add Bollinger Bands"""
        sma = df['close'].rolling(period).mean()
        std = df['close'].rolling(period).std()
        df['bb_upper'] = sma + (std * std_dev)
        df['bb_middle'] = sma
        df['bb_lower'] = sma - (std * std_dev)
        return df
    
    def check_all_conditions(self, df, symbol):
        """Check if stock meets ALL specified conditions"""
        if len(df) < 300:  # Need enough data for all calculations
            return None
            
        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        
        # All conditions must be True
        conditions = {
            '5_EMA_gt_20_SMA': latest['ema5'] > latest['sma20'],
            '13_EMA_gt_20_SMA': latest['ema13'] > latest['sma20'],
            '26_EMA_gt_20_SMA': latest['ema26'] > latest['sma20'],
            '50_SMA_gt_20_SMA': latest['sma50'] > latest['sma20'],
            '100_SMA_gt_20_SMA': latest['sma100'] > latest['sma20'],
            '200_SMA_gt_20_SMA': latest['sma200'] > latest['sma20'],
            'ADX_Positive_DI_ge_Negative_DI': latest['plus_di'] >= latest['minus_di'],
            'MACD_Line_ge_MACD_Signal': latest['macd_line'] >= latest['macd_signal'],
            'RSI_gt_40': latest['rsi'] > 40,
            'Stoch_RSI_gt_30': latest['stoch_rsi'] > 30,
            'Close_ge_Upper_BB': latest['close'] >= latest['bb_upper'],
            'Bullish_Candle': latest['close'] > latest['open'],
            'Volume_gt_100000': latest['volume'] > 100000,
            'Close_near_300d_high': latest['close'] * 1.05 > latest['high_300d'],
            'Close_gt_Prev_Close': latest['close'] > latest['prev_close'],
            'Volume_gt_50d_avg': latest['volume'] > latest['vol_50ma']
        }
        
        # Check if ALL conditions are met
        all_conditions_met = all(conditions.values())
        
        if all_conditions_met:
            # Calculate entry, stop loss, and target
            entry = latest['close']
            atr = df['high'].sub(df['low']).rolling(14).mean().iloc[-1]
            
            return {
                'Stock': symbol,
                'Entry': f"₹{entry:.2f}",
                'Stop Loss': f"₹{max(entry - atr * 2, latest['bb_lower']):.2f}",
                'Target': f"₹{entry + atr * 3:.2f}",
                'RSI': f"{latest['rsi']:.1f}",
                'Volume Ratio': f"{latest['vol_ratio']:.2f}x",
                'Conditions Met': f"{sum(conditions.values())}/16"
            }
        
        return None
    
    def scan_stocks(self, stock_list):
        """Scan all stocks for advanced conditions"""
        signals = []
        progress = st.progress(0)
        status_placeholder = st.empty()
        
        def analyze_stock(stock_data):
            instrument_key, symbol = stock_data
            df = self.get_data(instrument_key)
            if df is not None:
                return self.check_all_conditions(df, symbol)
            return None
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(analyze_stock, stock) for stock in stock_list]
            
            for i, future in enumerate(futures):
                try:
                    result = future.result()
                    if result:
                        signals.append(result)
                        st.success(f"✅ {result['Stock']} - ALL CONDITIONS MET!")
                    else:
                        stock_symbol = stock_list[i][1]
                        status_placeholder.info(f"⏳ Checking {stock_symbol}... ({i+1}/{len(stock_list)})")
                except Exception as e:
                    pass
                progress.progress((i + 1) / len(stock_list))
        
        status_placeholder.empty()
        return signals
    
    def send_telegram(self, signals):
        """Send advanced results to Telegram"""
        if not AUTO_CONFIG["telegram_bot_token"]:
            return False
            
        if not signals:
            message = "📈 No stocks found meeting ALL 16 conditions"
        else:
            message = f"🎯 {len(signals)} Stocks Found Meeting ALL 16 Advanced Conditions:\n\n"
            for i, s in enumerate(signals, 1):
                message += f"{i}. {s['Stock']}\n"
                message += f"Entry: {s['Entry']} | SL: {s['Stop Loss']} | Target: {s['Target']}\n"
                message += f"RSI: {s['RSI']} | Vol Ratio: {s['Volume Ratio']}\n\n"
        
        url = f"https://api.telegram.org/bot{AUTO_CONFIG['telegram_bot_token']}/sendMessage"
        try:
            requests.post(url, data={
                "chat_id": AUTO_CONFIG["telegram_chat_id"],
                "text": message
            })
            return True
        except:
            return False

def main():
    st.set_page_config(page_title="Advanced Stock Screener", layout="wide")
    st.title("🚀 Advanced Stock Screener - 16 Conditions Filter")
    
    # Display all conditions
    st.info("""
    📊 **16 STRICT CONDITIONS - ALL MUST BE MET:**
    • 5 EMA > 20 SMA • 13 EMA > 20 SMA • 26 EMA > 20 SMA
    • 50 SMA > 20 SMA • 100 SMA > 20 SMA • 200 SMA > 20 SMA
    • ADX +DI ≥ -DI • MACD Line ≥ Signal • RSI > 40 • Stoch RSI > 30
    • Close ≥ Upper Bollinger Band • Bullish Candle • Volume > 100K
    • Close × 1.05 > 300-day high • Close > Yesterday • Volume > 50-day avg
    """)
    
    # Load stocks
    uploaded_file = st.file_uploader("📁 Upload CSV (optional)", type=['csv'])
    if uploaded_file:
        csv_content = uploaded_file.getvalue().decode('utf-8')
    else:
        csv_content = AUTO_CONFIG["default_stocks"]
        st.info("📊 Using default 20 stocks")
    
    # Parse stocks
    try:
        df = pd.read_csv(StringIO(csv_content))
        stock_list = [(row['instrument_key'], row['tradingsymbol']) for _, row in df.iterrows()]
    except:
        st.error("❌ Invalid CSV format")
        return
    
    # Scan button
    if st.button("🔍 START ADVANCED SCAN", type="primary", use_container_width=True):
        screener = AdvancedStockScreener()
        
        with st.spinner(f"Scanning {len(stock_list)} stocks with 16 strict conditions..."):
            signals = screener.scan_stocks(stock_list)
        
        # Results
        if signals:
            st.success(f"🎯 Found {len(signals)} stocks meeting ALL 16 conditions!")
            
            # Display table
            df_results = pd.DataFrame(signals)
            st.dataframe(df_results, use_container_width=True)
            
            # Download
            csv_data = df_results.to_csv(index=False)
            st.download_button(
                "📥 Download Results", 
                csv_data, 
                f"advanced_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            )
            
            # Telegram
            if screener.send_telegram(signals):
                st.success("📱 Sent to Telegram!")
            else:
                st.warning("⚠️ Telegram failed")
        else:
            st.warning("😔 No stocks found meeting ALL 16 conditions")
            st.info("💡 Try with a larger stock universe or adjust some conditions")

if __name__ == "__main__":
    main()