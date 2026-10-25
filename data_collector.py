import ccxt
import pandas as pd
import os
from datetime import datetime, timedelta
import pytz
import time

# --- 配置参数 ---
SYMBOL = 'SOL/USDT'
TIMEFRAMES = ['5m', '15m', '30m', '1h', '2h']  # 5m/15m/30m/1h/2h
DAYS = 180  # 调整为 180 天
DATA_DIR = 'data'
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 创建数据目录
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


def remove_stale_4h_file():
    """清理历史 4h 数据文件，避免继续保留旧周期。"""
    stale_path = os.path.join(DATA_DIR, 'SOLUSDT_4h.csv')
    if os.path.exists(stale_path):
        os.remove(stale_path)
        print(f"[清理] 已删除旧的 4h 数据文件: {stale_path}")


def validate_and_clean_ohlcv(df, timeframe):
    """对抓取到的 OHLCV 数据做检查、清洗和时间戳规范化。"""
    if df is None or df.empty:
        return pd.DataFrame()

    clean_df = df.copy()
    clean_df.columns = [str(c).lower() for c in clean_df.columns]

    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing = [c for c in required_cols if c not in clean_df.columns]
    if missing:
        raise ValueError(f"{timeframe} 数据缺少必要字段: {missing}")

    clean_df = clean_df[required_cols].copy()
    clean_df['timestamp'] = pd.to_numeric(clean_df['timestamp'], errors='coerce')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce')

    # 清理 NaN 和异常值
    clean_df = clean_df.dropna(subset=['timestamp', 'open', 'high', 'low', 'close', 'volume']).reset_index(drop=True)
    if clean_df.empty:
        return clean_df

    # 去重：同一时间戳保留最后一条
    clean_df = clean_df.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last').reset_index(drop=True)

    # 过滤明显异常值：价格必须正数，且高>=低，开/收盘在价格区间内
    valid_mask = (
        (clean_df['open'] > 0)
        & (clean_df['high'] > 0)
        & (clean_df['low'] > 0)
        & (clean_df['close'] > 0)
        & (clean_df['high'] >= clean_df['low'])
        & (clean_df['high'] >= clean_df['open'])
        & (clean_df['high'] >= clean_df['close'])
        & (clean_df['low'] <= clean_df['open'])
        & (clean_df['low'] <= clean_df['close'])
    )
    clean_df = clean_df.loc[valid_mask].reset_index(drop=True)

    # 处理 volume 非负
    clean_df['volume'] = clean_df['volume'].clip(lower=0)

    # 规范化时间字段为毫秒精度
    clean_df['timestamp'] = clean_df['timestamp'].astype('int64')
    clean_df['datetime'] = pd.to_datetime(clean_df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(BEIJING_TZ)

    print(f"[检查] {timeframe} 数据清洗完成，剩余 {len(clean_df)} 条有效记录。")
    return clean_df


def align_all_timeframes_to_2h_end(frame_map):
    """以最后一根 2h K 线时间戳作为公共截断点，对齐所有周期数据的最后时间。"""
    if '2h' not in frame_map or frame_map['2h'].empty:
        return frame_map

    common_end_ts = frame_map['2h']['timestamp'].max()
    print(f"[对齐] 使用 2h 周期最后时间戳 {common_end_ts} 作为所有周期数据的公共结束时间。")

    for timeframe, df in frame_map.items():
        if df.empty:
            continue
        original_len = len(df)
        aligned_df = df[df['timestamp'] <= common_end_ts].copy().reset_index(drop=True)
        frame_map[timeframe] = aligned_df
        if len(aligned_df) != original_len:
            print(f"[对齐] {timeframe} 已按 2h 结束时间截断：{original_len} -> {len(aligned_df)}")

    return frame_map


def fetch_all_ohlcv(timeframe):
    """
    使用循环翻页逻辑抓取完整的 180 天数据，并在结束后执行清洗和对齐。
    """
    # 初始化 OKX 交易所 (开启速率限制)
    exchange = ccxt.okx({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}  # 使用永续合约数据
    })

    # 计算目标起始时间戳 (180天前)
    end_dt = datetime.now(BEIJING_TZ)
    start_dt = end_dt - timedelta(days=DAYS)
    target_since = int(start_dt.timestamp() * 1000)

    all_ohlcv = []
    current_since = target_since

    print(f"\n[任务开始] 正在获取 {SYMBOL} - {timeframe} 过去 {DAYS} 天的数据...")

    while True:
        try:
            # 抓取数据，limit 设为 1000
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
            time.sleep(5)  # 出错后等待重试
            continue

    if all_ohlcv:
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = validate_and_clean_ohlcv(df, timeframe)

        if not df.empty:
            filename = os.path.join(DATA_DIR, f'SOLUSDT_{timeframe}.csv')
            df.to_csv(filename, index=False)
            print(f"[完成] {timeframe} 数据已保存，共 {len(df)} 行记录。")
        else:
            print(f"[错误] {timeframe} 数据清洗后为空，未保存文件。")
    else:
        print(f"[错误] 未能获取到 {timeframe} 的任何数据。")


def build_common_timeframe_dataset():
    """读取所有周期数据，统一做清洗并以 2h 最后时间对齐。"""
    frame_map = {}
    for tf in TIMEFRAMES:
        file_path = os.path.join(DATA_DIR, f'SOLUSDT_{tf}.csv')
        if not os.path.exists(file_path):
            print(f"[跳过] 未找到 {tf} 数据文件: {file_path}")
            continue

        df = pd.read_csv(file_path)
        clean_df = validate_and_clean_ohlcv(df, tf)
        if not clean_df.empty:
            frame_map[tf] = clean_df

    frame_map = align_all_timeframes_to_2h_end(frame_map)

    for tf, df in frame_map.items():
        if df.empty:
            continue
        out_path = os.path.join(DATA_DIR, f'SOLUSDT_{tf}.csv')
        df.to_csv(out_path, index=False)
        print(f"[保存] 已写入对齐后的 {tf} 数据: {out_path}, 共 {len(df)} 条记录。")


if __name__ == "__main__":
    print(f"=== SOL 永续合约数据采集器 (180日全量+清洗+对齐版) ===")
    remove_stale_4h_file()
    for tf in TIMEFRAMES:
        fetch_all_ohlcv(tf)
    build_common_timeframe_dataset()
    print("\n所有周期数据更新完毕。")
