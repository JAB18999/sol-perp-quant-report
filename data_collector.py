import ccxt
import pandas as pd
from datetime import datetime, timedelta
import os
import pytz

# ==================== 配置 ====================
# 修改1: 交易对改为 OKX 的永续合约命名
SYMBOL = 'SOL-USDT-SWAP' 
TIMEFRAMES = ['15m', '30m', '1h', '2h']
DAYS = 60
DATA_DIR = 'data'

# 北京时间
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 创建数据目录
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_data(timeframe):
    # 修改2: 将交易所从 binance 改为 okx
    exchange = ccxt.okx({'enableRateLimit': True}) 
    filename = f"{DATA_DIR}/SOLUSDT_{timeframe.replace('/', '')}.csv"
    print(f"[{timeframe}] 开始抓取数据...")

    try:
        # 每次都抓取最近60天数据（不做增量，强制最新）
        since = int((datetime.now(BEIJING_TZ) - timedelta(days=DAYS)).timestamp() * 1000)
        
        # fetch_ohlcv 参数保持不变
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe, since=since, limit=1000)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 时间戳处理保持不变（ccxt.okx 返回的也是毫秒）
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(BEIJING_TZ)
        
        # 数据清洗
        df = df.drop_duplicates(subset=['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # 保存最新数据
        df.to_csv(filename, index=False)
        print(f"[{timeframe}] 保存成功！共 {len(df)} 条记录，最后时间：{df['timestamp'].iloc[-1]}")
        
    except Exception as e:
        print(f"[{timeframe}] 出错: {e}")

# 主程序
if __name__ == "__main__":
    print(f"🚀 开始执行 SOL 永续合约数据更新 - 北京时间: {datetime.now(BEIJING_TZ)}")
    
    # 每次运行前清空旧数据（确保只保留最新）
    for f in os.listdir(DATA_DIR):
        if f.endswith('.csv'):
            os.remove(os.path.join(DATA_DIR, f))
    
    for tf in TIMEFRAMES:
        fetch_data(tf)
    
    print("✅ 本次数据更新完成！仅保留最新文件。")
