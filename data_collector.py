import ccxt
import pandas as pd
import os
from datetime import datetime, timedelta
import pytz
import time

# --- 配置参数 ---
SYMBOL = 'SOL/USDT'
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h']
DAYS = 60  # 明确需求：下载 60 天数据
DATA_DIR = 'data'
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 创建数据目录
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def fetch_all_ohlcv(timeframe):
    """
    使用循环翻页逻辑抓取完整的 60 天数据
    """
    # 初始化 OKX 交易所 (开启速率限制)
    exchange = ccxt.okx({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'} # 使用永续合约数据
    })
    
    # 计算目标起始时间戳 (60天前)
    end_dt = datetime.now(BEIJING_TZ)
    start_dt = end_dt - timedelta(days=DAYS)
    target_since = int(start_dt.timestamp() * 1000)
    
    all_ohlcv = []
    current_since = target_since
    
    print(f"\n[任务开始] 正在获取 {SYMBOL} - {timeframe} 过去 {DAYS} 天的数据...")
    
    while True:
        try:
            # 抓取数据，limit 设为 1000 (OKX 最大通常支持 100-300，ccxt 会自动处理分页)
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe, since=current_since, limit=1000)
            
            if not ohlcv or len(ohlcv) == 0:
                break
            
            all_ohlcv.extend(ohlcv)
            
            # 获取最后一条数据的时间戳
            last_ts = ohlcv[-1][0]
            
            # 如果最后一条数据的时间已经接近现在，则停止
            if last_ts >= int(datetime.now(BEIJING_TZ).timestamp() * 1000) - 60000:
                break
            
            # 更新下一次请求的起始点 (最后一条的时间戳 + 1毫秒)
            current_since = last_ts + 1
            
            # 进度打印
            current_dt = datetime.fromtimestamp(last_ts / 1000, BEIJING_TZ).strftime('%Y-%m-%d %H:%M')
            print(f"  已同步至: {current_dt} | 累计获取: {len(all_ohlcv)} 条")
            
            # 频率控制，防止被封 IP
            time.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            print(f"  抓取异常: {e}")
            time.sleep(5) # 出错后等待重试
            continue

    if all_ohlcv:
        # 转换为 DataFrame
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 转换时间戳为可读格式 (方便检查)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(BEIJING_TZ)
        
        # 保存文件
        filename = f"{DATA_DIR}/SOLUSDT_{timeframe}.csv"
        df.to_csv(filename, index=False)
        print(f"[完成] {timeframe} 数据已保存，共 {len(df)} 行记录。")
    else:
        print(f"[错误] 未能获取到 {timeframe} 的任何数据。")

if __name__ == "__main__":
    print(f"=== SOL 永续合约数据采集器 (60日全量版) ===")
    for tf in TIMEFRAMES:
        fetch_all_ohlcv(tf)
    print("\n所有周期数据更新完毕。")
