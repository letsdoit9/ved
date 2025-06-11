# Enhanced Automated Stock Screener with Debug Features
import pandas as pd
import numpy as np
import requests
import streamlit as st
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import time

# 🔧 AUTO-CONFIGURATION - Edit these values once
AUTO_CONFIG = {
    "upstox_token": "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiJBSzg0NzUiLCJqdGkiOiI2ODQzZmFkMzI1NDU5YTJlZGZlMTkzNzMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc0OTI4NTU4NywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzQ5MzMzNjAwfQ.FIxAD2G4saQbG9MgKj7wBsswsDmVpcS5RLmUkUPiAQ4",
    "telegram_bot_token": "7923075723:AAGL5-DGPSU0TLb68vOLretVwioC6vK0fJk", 
    "telegram_chat_id": "457632002",
    "default_stocks": """instrument_key,tradingsymbol
NSE_EQ|INE585B01010,MARUTI
NSE_EQ|INE139A01034,NATIONALUM
NSE_EQ|INE763I01026,TARIL
NSE_EQ|INE970X01018,LEMONTREE
NSE_EQ|INE522D01027,MANAPPURAM
NSE_EQ|INE917I01010,BAJAJ-AUTO
NSE_EQ|INE267A01025,HINDZINC
NSE_EQ|INE070A01015,SHREECEM
NSE_EQ|INE749A01030,JINDALSTEL
NSE_EQ|INE160A01022,PNB"""
}

class EnhancedStockScreener:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {AUTO_CONFIG["upstox_token"]}',
            'Content-Type': 'application/json'
        })
        self.debug_info = []
    
    def get_data(self, instrument_key):
        """Get stock data with error handling"""
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')
            url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
            
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 401:
                st.error("❌ Token expired! Please update your Upstox token.")
                return None
            elif response.status_code != 200:
                st.warning(f"⚠️ API Error {response.status_code} for {instrument_key}")
                return None
                
            data = response.json()
            
            if data.get('status') != 'success':
                st.warning(f"⚠️ API returned error for {instrument_key}: {data.get('message', 'Unknown error')}")
                return None
                
            candles = data.get('data', {}).get('candles', [])
            if not candles:
                st.warning(f"⚠️ No data available for {instrument_key}")
                return None
                
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            return df.sort_values('timestamp').reset_index(drop=True)
            
        except requests.exceptions.Timeout:
            st.warning(f"⏰ Timeout for {instrument_key}")
            return None
        except Exception as e:
            st.warning(f"❌ Error for {instrument_key}: {str(e)}")
            return None
    
    def calculate_indicators(self, df):
        """Calculate all indicators with safety checks"""
        try:
            # RSI
            df['rsi'] = self.rsi(df['close'])
            
            # ATR
            df['atr'] = self.atr(df)
            
            # EMAs
            df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
            df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
            
            # Volume MA
            df['vol_ma'] = df['volume'].rolling(window=20, min_periods=10).mean()
            
            return df
        except Exception as e:
            st.error(f"Error calculating indicators: {e}")
            return df
    
    def rsi(self, prices, period=14):
        """RSI calculation with safety checks"""
        try:
            delta = prices.diff()
            gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=period//2).mean()
            loss = -delta.where(delta < 0, 0).rolling(window=period, min_periods=period//2).mean()
            
            # Avoid division by zero
            loss = loss.replace(0, 0.0001)
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.fillna(50)  # Fill NaN with neutral RSI
        except:
            return pd.Series([50] * len(prices), index=prices.index)
    
    def atr(self, df, period=14):
        """ATR calculation with safety checks"""
        try:
            high, low, close = df['high'], df['low'], df['close']
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            return tr.rolling(window=period, min_periods=period//2).mean().fillna(tr.mean())
        except:
            return pd.Series([1.0] * len(df), index=df.index)
    
    def check_signal_with_debug(self, df, symbol):
        """Check signal with detailed debugging"""
        if len(df) < 30:
            self.debug_info.append(f"{symbol}: Insufficient data ({len(df)} days)")
            return None
            
        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        
        # Get recent highs for breakout check
        recent_highs = df.iloc[-5:-1]['high'] if len(df) > 5 else df.iloc[:-1]['high']
        
        # Signal conditions with debugging
        rsi_value = latest['rsi']
        rsi_ok = 30 <= rsi_value <= 70
        
        ema9_value = latest['ema9']
        ema21_value = latest['ema21']
        trend_ok = ema9_value > ema21_value
        
        volume_ratio = latest['volume'] / latest['vol_ma'] if latest['vol_ma'] > 0 else 0
        volume_ok = volume_ratio > 1.2  # Reduced threshold
        
        recent_high = recent_highs.max() if len(recent_highs) > 0 else latest['close']
        breakout_ok = latest['close'] > recent_high * 1.002  # Reduced threshold (0.2%)
        
        # Debug information
        debug_msg = f"{symbol}: RSI={rsi_value:.1f}({rsi_ok}), Trend={trend_ok}({ema9_value:.2f}>{ema21_value:.2f}), Vol={volume_ratio:.1f}x({volume_ok}), Breakout={breakout_ok}({latest['close']:.2f}>{recent_high:.2f})"
        self.debug_info.append(debug_msg)
        
        conditions_met = sum([rsi_ok, trend_ok, volume_ok, breakout_ok])
        
        # Lower threshold for signal generation
        if conditions_met >= 3:  # Changed from 4 to 3
            entry = latest['close']
            atr = latest['atr']
            return {
                'Stock': symbol,
                'Entry': f"₹{entry:.2f}",
                'Stop Loss': f"₹{max(entry - atr * 1.8, entry * 0.95):.2f}",  # Max 5% SL
                'Target': f"₹{entry + atr * 2.5:.2f}",
                'RSI': f"{rsi_value:.1f}",
                'Volume': f"{volume_ratio:.1f}x",
                'Conditions': f"{conditions_met}/4",
                'Price': entry
            }
        return None
    
    def scan_stocks_enhanced(self, stock_list, max_stocks=10):
        """Enhanced stock scanning with better error handling"""
        signals = []
        self.debug_info = []
        
        # Limit stocks for faster testing
        test_stocks = stock_list[:max_stocks]
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, (instrument_key, symbol) in enumerate(test_stocks):
            status_text.text(f"Analyzing {symbol}... ({i+1}/{len(test_stocks)})")
            
            # Add small delay to avoid rate limiting
            time.sleep(0.1)
            
            df = self.get_data(instrument_key)
            if df is not None:
                signal = self.check_signal_with_debug(df, symbol)
                if signal:
                    signals.append(signal)
                    st.success(f"✅ Signal: {symbol} - {signal['Conditions']} conditions met")
            
            progress_bar.progress((i + 1) / len(test_stocks))
        
        status_text.empty()
        return signals
    
    def send_telegram(self, signals):
        """Send to Telegram with better formatting"""
        if not AUTO_CONFIG["telegram_bot_token"]:
            return False
            
        if not signals:
            message = "📈 No signals found in current scan"
        else:
            message = f"📈 {len(signals)} Stock Signals Found:\n\n"
            for i, s in enumerate(signals, 1):
                message += f"{i}. *{s['Stock']}* ({s['Conditions']})\n"
                message += f"Entry: {s['Entry']} | SL: {s['Stop Loss']} | Target: {s['Target']}\n"
                message += f"RSI: {s['RSI']} | Volume: {s['Volume']}\n\n"
        
        url = f"https://api.telegram.org/bot{AUTO_CONFIG['telegram_bot_token']}/sendMessage"
        try:
            response = requests.post(url, data={
                "chat_id": AUTO_CONFIG["telegram_chat_id"],
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)
            return response.status_code == 200
        except:
            return False

def main():
    st.set_page_config(page_title="Enhanced Auto Stock Screener", layout="wide")
    st.title("🚀 Enhanced Auto Stock Screener")
    st.info("✨ Enhanced version with debugging and relaxed conditions!")
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        max_stocks = st.slider("Max stocks to scan", 5, 50, 10)
        show_debug = st.checkbox("Show debug info", True)
        
        st.header("📊 Signal Conditions")
        st.write("- RSI: 30-70 (momentum)")
        st.write("- EMA9 > EMA21 (trend)")
        st.write("- Volume > 1.2x average")
        st.write("- Price breakout (0.2%)")
        st.write("- **Need 3/4 conditions** ⭐")
    
    # Load stocks
    uploaded_file = st.file_uploader("📁 Upload CSV (optional)", type=['csv'])
    if uploaded_file:
        csv_content = uploaded_file.getvalue().decode('utf-8')
        st.success("📊 Using uploaded stock list")
    else:
        csv_content = AUTO_CONFIG["default_stocks"]
        st.info(f"📊 Using default {len(csv_content.split()) - 1} stocks for testing")
    
    # Parse stocks
    try:
        df = pd.read_csv(StringIO(csv_content))
        stock_list = [(row['instrument_key'], row['tradingsymbol']) for _, row in df.iterrows()]
        st.success(f"✅ Loaded {len(stock_list)} stocks")
    except Exception as e:
        st.error(f"❌ Invalid CSV format: {e}")
        return
    
    # Scan button
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 START SCAN", type="primary", use_container_width=True):
            screener = EnhancedStockScreener()
            
            start_time = time.time()
            with st.spinner(f"Scanning top {max_stocks} stocks..."):
                signals = screener.scan_stocks_enhanced(stock_list, max_stocks)
            
            scan_time = time.time() - start_time
            
            # Results
            if signals:
                st.success(f"🎯 Found {len(signals)} signals in {scan_time:.1f}s!")
                
                # Sort by conditions met and price
                signals_df = pd.DataFrame(signals)
                signals_df = signals_df.sort_values(['Conditions', 'Price'], ascending=[False, False])
                
                # Display results
                st.dataframe(signals_df, use_container_width=True)
                
                # Download
                csv_data = signals_df.to_csv(index=False)
                st.download_button(
                    "📥 Download CSV", 
                    csv_data, 
                    f"signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
                
                # Send to Telegram
                if screener.send_telegram(signals):
                    st.success("📱 Sent to Telegram!")
                else:
                    st.warning("⚠️ Telegram failed (check token/chat_id)")
                    
            else:
                st.warning("😔 No signals found with current criteria")
                st.info("💡 Try increasing the scan size or check debug info below")
            
            # Debug information
            if show_debug and screener.debug_info:
                with st.expander("🔍 Debug Information", expanded=False):
                    for debug_msg in screener.debug_info[-10:]:  # Show last 10
                        st.text(debug_msg)
    
    with col2:
        if st.button("🧪 TEST API", use_container_width=True):
            screener = EnhancedStockScreener()
            test_stock = stock_list[0]  # Test first stock
            
            with st.spinner(f"Testing API with {test_stock[1]}..."):
                df = screener.get_data(test_stock[0])
                
            if df is not None:
                st.success(f"✅ API working! Got {len(df)} days of data for {test_stock[1]}")
                st.write(f"Latest close: ₹{df.iloc[-1]['close']:.2f}")
                st.write(f"Volume: {df.iloc[-1]['volume']:,.0f}")
            else:
                st.error("❌ API test failed! Check your token.")
    
    # Token status
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        token_status = "🟢 Valid" if AUTO_CONFIG["upstox_token"] else "🔴 Missing"
        st.metric("Upstox Token", token_status)
    
    with col2:
        tg_status = "🟢 Set" if AUTO_CONFIG["telegram_bot_token"] else "🔴 Missing"
        st.metric("Telegram Bot", tg_status)
    
    with col3:
        chat_status = "🟢 Set" if AUTO_CONFIG["telegram_chat_id"] else "🔴 Missing"
        st.metric("Chat ID", chat_status)

if __name__ == "__main__":
    main()