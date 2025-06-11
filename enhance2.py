import pandas as pd
import numpy as np
import requests
import streamlit as st
from datetime import datetime, timedelta
import talib
from io import StringIO
import time
import json

# Configuration
CONFIG = {
    "upstox_token": "",  # Leave empty - will be set via UI
    "telegram_bot_token": "7923075723:AAGL5-DGPSU0TLb68vOLretVwioC6vK0fJk",
    "telegram_chat_id": "457632002",
    "stocks": """instrument_key,tradingsymbol
NSE_EQ|INE585B01010,MARUTI
NSE_EQ|INE139A01034,NATIONALUM
NSE_EQ|INE763I01026,TARIL
NSE_EQ|INE970X01018,LEMONTREE
NSE_EQ|INE522D01027,MANAPPURAM
NSE_EQ|INE917I01010,BAJAJ-AUTO
NSE_EQ|INE267A01025,HINDZINC
NSE_EQ|INE070A01015,SHREECEM
NSE_EQ|INE749A01030,JINDALSTEL
NSE_EQ|INE160A01022,PNB
NSE_EQ|INE002A01018,RELIANCE
NSE_EQ|INE009A01021,INFY
NSE_EQ|INE467B01029,ASIANPAINT
NSE_EQ|INE040A01034,HDFC
NSE_EQ|INE021A01026,KOTAKBANK"""
}

class StockScreener:
    def __init__(self, token=None):
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers.update({
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            })
    
    def update_token(self, new_token):
        """Update the API token"""
        self.token = new_token
        self.session.headers.update({
            'Authorization': f'Bearer {new_token}',
            'Content-Type': 'application/json'
        })
    
    def test_token_validity(self):
        """Test if the current token is valid"""
        if not self.token:
            return False, "No token provided"
        
        test_url = "https://api.upstox.com/v2/user/profile"
        try:
            response = self.session.get(test_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    user_name = data.get('data', {}).get('user_name', 'Unknown')
                    return True, f"Token valid for user: {user_name}"
                else:
                    return False, "Token invalid - API returned error"
            elif response.status_code == 401:
                return False, "Token expired or invalid"
            else:
                return False, f"API error: {response.status_code}"
        except requests.exceptions.RequestException as e:
            return False, f"Connection error: {str(e)}"
    
    def get_data(self, instrument_key):
        """Fetch historical data for a stock"""
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
            url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/day/{to_date}/{from_date}"
            
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 401:
                st.error("🔴 Token expired during data fetch!")
                return None
            elif response.status_code != 200:
                st.warning(f"API Error {response.status_code} for {instrument_key}")
                return None
                
            data = response.json()
            if data.get('status') != 'success':
                return None
                
            candles = data.get('data', {}).get('candles', [])
            if len(candles) < 210:  # Need enough data for 200 SMA
                return None
                
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            return df.sort_values('timestamp').reset_index(drop=True)
            
        except Exception as e:
            st.error(f"Error fetching data for {instrument_key}: {str(e)}")
            return None
    
    def calculate_indicators(self, df):
        """Calculate all technical indicators"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        # EMAs and SMAs
        df['ema5'] = talib.EMA(close, timeperiod=5)
        df['ema13'] = talib.EMA(close, timeperiod=13)
        df['ema26'] = talib.EMA(close, timeperiod=26)
        df['sma50'] = talib.SMA(close, timeperiod=50)
        df['sma100'] = talib.SMA(close, timeperiod=100)
        df['sma200'] = talib.SMA(close, timeperiod=200)
        
        # ADX and DI
        df['adx'] = talib.ADX(high, low, close, timeperiod=10)
        df['plus_di'] = talib.PLUS_DI(high, low, close, timeperiod=10)
        df['minus_di'] = talib.MINUS_DI(high, low, close, timeperiod=10)
        
        # MACD
        df['macd'], df['macd_signal'], _ = talib.MACD(close, fastperiod=14, slowperiod=5, signalperiod=3)
        
        # RSI and Stochastic RSI
        df['rsi'] = talib.RSI(close, timeperiod=14)
        df['stoch_rsi'] = talib.STOCHRSI(close, timeperiod=14)[0] * 100
        
        # Bollinger Bands
        df['bb_upper'], _, _ = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        
        # Volume MA
        df['vol_ma50'] = talib.SMA(volume, timeperiod=50)
        
        return df
    
    def check_all_16_conditions(self, df, symbol):
        """Check ALL 16 conditions including enhanced validation"""
        if len(df) < 210:
            return None
            
        df = self.calculate_indicators(df)
        current = df.iloc[-1]
        yesterday = df.iloc[-2]
        
        # All 16 conditions with proper null checks
        conditions = [
            current['ema5'] > 20 and not pd.isna(current['ema5']),
            current['ema13'] > 20 and not pd.isna(current['ema13']),
            current['ema26'] > 20 and not pd.isna(current['ema26']),
            current['sma50'] > 20 and not pd.isna(current['sma50']),
            current['sma100'] > 20 and not pd.isna(current['sma100']),
            current['sma200'] > 20 and not pd.isna(current['sma200']),
            (current['plus_di'] >= current['minus_di']) and not pd.isna(current['plus_di']) and not pd.isna(current['minus_di']),
            (current['macd'] >= current['macd_signal']) and not pd.isna(current['macd']) and not pd.isna(current['macd_signal']),
            current['rsi'] > 40 and not pd.isna(current['rsi']),
            current['stoch_rsi'] > 50 and not pd.isna(current['stoch_rsi']),
            (current['close'] >= current['bb_upper']) and not pd.isna(current['bb_upper']),
            current['close'] > current['open'],
            current['volume'] > 100000,
            current['close'] * 1.05 > df['high'].rolling(200).max().iloc[-1],
            current['close'] > yesterday['close'],
            (current['volume'] > current['vol_ma50']) and not pd.isna(current['vol_ma50']) and current['vol_ma50'] > 0
        ]
        
        conditions_met = sum(conditions)
        
        # Debug info for failed conditions
        if conditions_met < 16:
            condition_names = [
                "5 EMA > 20", "13 EMA > 20", "26 EMA > 20", "50 SMA > 20", "100 SMA > 20", "200 SMA > 20",
                "+DI ≥ -DI", "MACD ≥ Signal", "RSI > 40", "Stoch RSI > 50", "Close ≥ BB Upper",
                "Bullish Candle", "Volume > 100K", "Close × 1.05 > 200H", "Close > Yesterday", "Volume > 50MA"
            ]
            failed_conditions = [condition_names[i] for i, met in enumerate(conditions) if not met]
            st.write(f"🔍 {symbol}: {conditions_met}/16 - Failed: {', '.join(failed_conditions[:3])}...")
        
        # Must satisfy ALL 16 conditions
        if all(conditions):
            vol_ratio = current['volume'] / current['vol_ma50'] if current['vol_ma50'] > 0 else 0
            atr = talib.ATR(df['high'].values, df['low'].values, df['close'].values, timeperiod=14).iloc[-1]
            
            return {
                'Stock': symbol,
                'Entry': f"₹{current['close']:.2f}",
                'Stop Loss': f"₹{max(current['close'] - atr * 2, current['close'] * 0.95):.2f}",
                'Target': f"₹{current['close'] + atr * 3:.2f}",
                'RSI': f"{current['rsi']:.1f}",
                'Volume Ratio': f"{vol_ratio:.1f}x",
                'Conditions': "16/16 ✅",
                'Price': current['close']
            }
        
        return None
    
    def scan_stocks(self, stock_list):
        """Scan all stocks for signals"""
        signals = []
        progress = st.progress(0)
        status = st.empty()
        
        for i, (instrument_key, symbol) in enumerate(stock_list):
            status.text(f"Scanning {symbol}... ({i+1}/{len(stock_list)})")
            time.sleep(0.1)  # Rate limiting
            
            df = self.get_data(instrument_key)
            if df is not None:
                signal = self.check_all_16_conditions(df, symbol)
                if signal:
                    signals.append(signal)
                    st.success(f"✅ {symbol} - ALL 16 conditions met!")
            
            progress.progress((i + 1) / len(stock_list))
        
        status.empty()
        progress.empty()
        return signals
    
    def send_telegram(self, signals):
        """Send results to Telegram"""
        if not CONFIG["telegram_bot_token"] or not signals:
            return False
            
        message = f"🎯 {len(signals)} Stocks Meeting ALL 16 Conditions:\n\n"
        for i, s in enumerate(signals, 1):
            message += f"{i}. *{s['Stock']}* - {s['Entry']}\n"
            message += f"SL: {s['Stop Loss']} | Target: {s['Target']}\n"
            message += f"RSI: {s['RSI']} | Vol: {s['Volume Ratio']}\n\n"
        
        try:
            url = f"https://api.telegram.org/bot{CONFIG['telegram_bot_token']}/sendMessage"
            response = requests.post(url, data={
                "chat_id": CONFIG["telegram_chat_id"],
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)
            return response.status_code == 200
        except:
            return False

def main():
    st.set_page_config(page_title="Enhanced NSE Stock Screener", layout="wide")
    st.title("🎯 Enhanced NSE Stock Screener - ALL 16 CONDITIONS")
    
    # Token input section
    st.sidebar.header("🔑 API Configuration")
    
    with st.sidebar:
        st.markdown("### Upstox Token Setup")
        st.markdown("""
        1. Go to [Upstox Developer Console](https://api.upstox.com/)
        2. Login with your credentials
        3. Go to **Apps** → **Your App**
        4. Click **Generate Token**
        5. Copy the token and paste below
        """)
        
        token_input = st.text_input(
            "Enter Upstox API Token:",
            type="password",
            help="Paste your fresh Upstox API token here"
        )
        
        if token_input:
            CONFIG["upstox_token"] = token_input
            st.success("✅ Token updated!")
    
    # Initialize screener
    if CONFIG["upstox_token"]:
        screener = StockScreener(CONFIG["upstox_token"])
        
        # Test token validity
        is_valid, message = screener.test_token_validity()
        if is_valid:
            st.success(f"🟢 {message}")
        else:
            st.error(f"🔴 {message}")
            st.stop()
    else:
        st.warning("⚠️ Please enter your Upstox API token in the sidebar to continue")
        st.stop()
    
    st.info("🔥 This screener finds stocks that meet ALL 16 technical conditions simultaneously!")
    
    # Display all 16 conditions
    with st.expander("📋 All 16 Required Conditions", expanded=False):
        st.markdown("""
        **Moving Averages (All > 20):**
        1. 5 EMA > 20 | 2. 13 EMA > 20 | 3. 26 EMA > 20 | 4. 50 SMA > 20 | 5. 100 SMA > 20 | 6. 200 SMA > 20
        
        **Momentum Indicators:**
        7. ADX +DI ≥ -DI | 8. MACD ≥ Signal | 9. RSI > 40 | 10. Stoch RSI > 50
        
        **Price & Volume Conditions:**
        11. Close ≥ BB Upper | 12. Bullish Candle | 13. Volume > 100K | 14. Close × 1.05 > 200H | 15. Close > Yesterday | 16. Volume > 50MA
        """)
    
    # Load stocks
    uploaded_file = st.file_uploader("📁 Upload Stock List (CSV)", type=['csv'])
    if uploaded_file:
        csv_content = uploaded_file.getvalue().decode('utf-8')
        st.success("📊 Using uploaded stock list")
    else:
        csv_content = CONFIG["stocks"]
        st.info("📊 Using default stock list (15 stocks)")
    
    try:
        df = pd.read_csv(StringIO(csv_content))
        stock_list = [(row['instrument_key'], row['tradingsymbol']) for _, row in df.iterrows()]
        st.success(f"✅ Loaded {len(stock_list)} stocks for scanning")
    except Exception as e:
        st.error(f"❌ CSV Error: {e}")
        return
    
    # Main scanning section
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚀 START COMPREHENSIVE SCAN", type="primary", use_container_width=True):
            start_time = time.time()
            
            with st.spinner("🔍 Scanning for stocks meeting ALL 16 conditions..."):
                signals = screener.scan_stocks(stock_list)
            
            scan_time = time.time() - start_time
            
            if signals:
                st.balloons()
                st.success(f"🎉 Found {len(signals)} stocks meeting ALL 16 conditions in {scan_time:.1f}s!")
                
                # Sort by price for better display
                signals_df = pd.DataFrame(signals)
                signals_df = signals_df.sort_values('Price', ascending=False)
                
                # Display results
                st.dataframe(signals_df.drop('Price', axis=1), use_container_width=True)
                
                # Download option
                csv_data = signals_df.to_csv(index=False)
                st.download_button(
                    "📥 Download Results",
                    csv_data,
                    f"16condition_stocks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                # Send to Telegram
                if screener.send_telegram(signals):
                    st.success("📱 Results sent to Telegram!")
                
            else:
                st.warning("😔 No stocks found meeting ALL 16 conditions")
                st.info("💡 This is normal - the conditions are very strict. Try scanning during different market conditions.")
    
    with col2:
        if st.button("🧪 Test Single Stock", use_container_width=True):
            test_stock = ("NSE_EQ|INE585B01010", "MARUTI")
            
            with st.spinner(f"Testing {test_stock[1]}..."):
                df = screener.get_data(test_stock[0])
            
            if df is not None:
                st.success(f"✅ Data fetched! {len(df)} days for {test_stock[1]}")
                
                # Show current price and volume
                current = df.iloc[-1]
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("Latest Price", f"₹{current['close']:.2f}")
                with col_b:
                    st.metric("Volume", f"{current['volume']:,.0f}")
                
                # Test conditions
                signal = screener.check_all_16_conditions(df, test_stock[1])
                if signal:
                    st.success("🎯 ALL 16 conditions met!")
                else:
                    st.info("📊 Not all conditions met - check debug info above")
            else:
                st.error("❌ Failed to fetch data")
    
    # Status dashboard
    st.markdown("---")
    st.subheader("📊 Status Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        token_status = "🟢 Valid" if CONFIG["upstox_token"] else "🔴 Missing"
        st.metric("API Token", token_status)
    
    with col2:
        tg_status = "🟢 Set" if CONFIG["telegram_bot_token"] else "🔴 Missing"
        st.metric("Telegram Bot", tg_status)
    
    with col3:
        st.metric("Conditions", "16/16 Required")
    
    with col4:
        st.metric("Stocks Loaded", len(stock_list) if 'stock_list' in locals() else 0)

if __name__ == "__main__":
    main()