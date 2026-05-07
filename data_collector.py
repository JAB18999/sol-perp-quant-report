import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import time

# ==================== 配置 ====================
SYMBOL = 'SOL/USDT:USDT'
TIMEFRAMES = ['15m', '30m', '1h', '2h']
DAYS = 60
DATA_DIR = 'data'

# 创建数据目录
os.makedirs(DATA_DIR, exist_ok=True)

# 时区设置为北京时间 (东八区)
import pytz
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def fetch_incremental_data(timeframe):
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
    
    filename = f"{DATA_DIR}/SOLUSDT_{timeframe.replace('/', '')}.csv"
    since = None
    
    # 如果文件已存在，读取最后时间戳做增量更新
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        if not df.empty:
            last_ts = pd.to_datetime(df['timestamp'].iloc[-1])
            since = int(last_ts.timestamp() * 1000) + 1
    
    print(f"[{timeframe}] 开始抓取数据...")

    all_data = []
    now = datetime.now(BEIJING_TZ)
    start_time = now - timedelta(days=DAYS)
    
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe, since=since, limit=1000)
        all_data.extend(ohlcv)
        
        df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(BEIJING_TZ)
        
        # 清洗数据
        df = df.drop_duplicates(subset=['timestamp'])
        df = df.sort_values('timestamp')
        df = df[df['timestamp'] >= start_time]  # 保留最近60天
        
        # 保存
        df.to_csv(filename, index=False)
        print(f"[{timeframe}] 保存成功！共 {len(df)} 条记录，最后时间：{df['timestamp'].iloc[-1]}")
        
    except Exception as e:
        print(f"[{timeframe}] 出错: {e}")

# 执行所有时间周期
if __name__ == "__main__":
    for tf in TIMEFRAMES:
        fetch_incremental_data(tf)
    print("✅ 所有数据更新完成！")
