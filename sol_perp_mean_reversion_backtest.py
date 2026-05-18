import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from itertools import product
import warnings
warnings.filterwarnings("ignore")

# ===================== 全局统一命名配置（全文件同名对齐） =====================
SCRIPT_NAME = "sol_perp_mean_reversion_backtest"
REPORT_NAME = f"{SCRIPT_NAME}_report.md"
DATA_DIR = "./data"
REPORT_SAVE_PATH = os.path.join(DATA_DIR, REPORT_NAME)

# 策略参数网格
MA_WINDOWS = [5, 10, 20, 30]
ENTRY_THRESHOLDS = [0.01, 0.02, 0.03, 0.05]
EXIT_THRESHOLDS = [0.005, 0.01, 0.02]
STOP_LOSS_RATIO = 0.03
TAKE_PROFIT_RATIO = 0.06
FEE_RATE = 0.0005
SLIPPAGE = 0.0002       # 模拟滑点
INIT_CAPITAL = 10000
MAX_POS_RATIO = 0.8
# ==========================================================================

def del_old_report():
    """运行前删除旧版回测报告"""
    if os.path.exists(REPORT_SAVE_PATH):
        os.remove(REPORT_SAVE_PATH)
        print(f"✅ 已删除旧报告: {REPORT_SAVE_PATH}")

def get_all_csv_files(folder):
    """获取data下所有csv文件路径+文件名"""
    csv_list = []
    for f in os.listdir(folder):
        if f.lower().endswith(".csv"):
            full_path = os.path.join(folder, f)
            csv_list.append({"file_name": f, "file_path": full_path})
    return csv_list

def load_single_csv(file_path):
    """读取单个CSV行情数据，统一时间与价格字段"""
    df = pd.read_csv(file_path)
    # 自动适配常见时间列
    time_cols = ["timestamp", "datetime", "time", "date"]
    t_col = None
    for c in time_cols:
        if c in df.columns:
            t_col = c
            break
    if t_col:
        df[t_col] = pd.to_datetime(df[t_col])
        df = df.sort_values(t_col).reset_index(drop=True)
    # 确保存在收盘价
    if "close" not in df.columns:
        raise Exception(f"文件 {file_path} 缺少 close 收盘价字段")
    df = df.dropna(subset=["close"])
    return df

def calc_regression_signal(df, ma_win, entry_thres, exit_thres):
    """计算均值回归多空信号"""
    data = df.copy()
    data["ma"] = data["close"].rolling(window=ma_win).mean()
    data["dev"] = (data["close"] - data["ma"]) / data["ma"]
    data.dropna(inplace=True)
    data["signal"] = 0
    # 超跌做多，超涨做空
    data.loc[data["dev"] <= -entry_thres, "signal"] = 1
    data.loc[data["dev"] >= entry_thres, "signal"] = -1
    # 回归均值平仓
    long_flat = (data["dev"] >= -exit_thres) & (data["signal"].shift(1) == 1)
    short_flat = (data["dev"] <= exit_thres) & (data["signal"].shift(1) == -1)
    data.loc[long_flat, "signal"] = 0
    data.loc[short_flat, "signal"] = 0
    return data

def single_backtest(df_signal, sl, tp, fee, slip, init_cap, pos_ratio):
    """单组参数回测，计入手续费+滑点"""
    capital = init_cap
    position = 0.0
    direction = 0
    open_price = 0.0
    trade_log = []
    net_asset = []

    for _, row in df_signal.iterrows():
        price = row["close"]
        sig = row["signal"]
        asset = capital + position * price
        net_asset.append(asset)

        if direction == 0 and sig != 0:
            trade_money = asset * pos_ratio
            vol = trade_money / price
            vol = max(vol, 0.001)
            real_open = price * (1 + slip) if sig == 1 else price * (1 - slip)
            open_price = real_open

            if sig == 1:
                position += vol
                direction = 1
            else:
                position -= vol
                direction = -1
            capital -= abs(vol) * real_open * fee

        elif direction != 0:
            real_close = price * (1 - slip) if direction == 1 else price * (1 + slip)
            if direction == 1:
                pct = (real_close - open_price) / open_price
                if pct >= tp or pct <= -sl or sig == 0:
                    capital += position * real_close
                    capital -= abs(position) * real_close * fee
                    trade_log.append({"dir":"多", "open":open_price,"close":real_close,"pct":round(pct,4)})
                    position = 0
                    direction = 0
            else:
                pct = (open_price - real_close) / open_price
                if pct >= tp or pct <= -sl or sig == 0:
                    capital += abs(position) * (open_price - real_close) + capital
                    capital -= abs(position) * real_close * fee
                    trade_log.append({"dir":"空", "open":open_price,"close":real_close,"pct":round(pct,4)})
                    position = 0
                    direction = 0

    final_asset = capital + position * df_signal["close"].iloc[-1]
    total_ret = (final_asset - init_cap) / init_cap
    win_num = sum(1 for t in trade_log if t["pct"] > 0)
    total_num = len(trade_log)
    win_rate = win_num / total_num if total_num > 0 else 0

    return {
        "final_asset": round(final_asset,2),
        "total_return": round(total_ret,4),
        "win_rate": round(win_rate,3),
        "trade_count": total_num,
        "trade_list": trade_log,
        "asset_curve": net_asset
    }

def grid_search_best_params(df):
    """单文件内网格寻优获取最优参数"""
    best_ret = -9999
    best_param = None
    best_res = None
    for ma, e_th, x_th in product(MA_WINDOWS, ENTRY_THRESHOLDS, EXIT_THRESHOLDS):
        sig_df = calc_regression_signal(df, ma, e_th, x_th)
        if len(sig_df) < 30:
            continue
        res = single_backtest(sig_df, STOP_LOSS_RATIO, TAKE_PROFIT_RATIO,
                              FEE_RATE, SLIPPAGE, INIT_CAPITAL, MAX_POS_RATIO)
        if res["total_return"] > best_ret:
            best_ret = res["total_return"]
            best_param = {"ma_win":ma, "entry_thres":e_th, "exit_thres":x_th}
            best_res = res
    if not best_param:
        return None, None
    return best_param, best_res

def generate_markdown_report(all_result_list):
    """整合所有CSV回测结果，生成标准MD报告"""
    md_content = f"# {SCRIPT_NAME} 均值回归策略回测综合报告\n\n"
    md_content += f"**报告生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    md_content += f"**策略类型**: SOL永续合约 价格-均线偏离均值回归策略\n"
    md_content += f"**初始本金**: {INIT_CAPITAL} USDT\n"
    md_content += f"**手续费率**: {FEE_RATE:.4f} | 滑点: {SLIPPAGE:.4f}\n"
    md_content += f"**固定止盈**: {TAKE_PROFIT_RATIO:.2%} | 固定止损: {STOP_LOSS_RATIO:.2%}\n\n"

    # 全局汇总统计
    total_file = len(all_result_list)
    profit_file = sum(1 for item in all_result_list if item["result"]["total_return"]>0)
    loss_file = total_file - profit_file
    avg_ret = np.mean([item["result"]["total_return"] for item in all_result_list])
    avg_winrate = np.mean([item["result"]["win_rate"] for item in all_result_list])

    md_content += "## 一、全局整体回测汇总\n"
    md_content += f"- 总计回测数据文件数量：{total_file} 个\n"
    md_content += f"- 盈利标的数量：{profit_file} 个\n"
    md_content += f"- 亏损标的数量：{loss_file} 个\n"
    md_content += f"- 所有标的平均收益率：{avg_ret:.2%}\n"
    md_content += f"- 所有标的平均交易胜率：{avg_winrate:.2%}\n\n"

    # 单文件明细
    md_content += "## 二、单个CSV文件回测明细\n\n"
    md_content += "| 数据文件名 | 最优均线周期 | 开仓偏离阈值 | 平仓偏离阈值 | 总收益率 | 交易胜率 | 交易次数 | 期末总资产 |\n"
    md_content += "|------------|-------------|-------------|-------------|----------|----------|----------|------------|\n"

    global_best_ret = -9999
    global_best_item = None

    for item in all_result_list:
        fname = item["file_name"]
        p = item["best_param"]
        res = item["result"]
        if not p:
            md_content += f"| {fname} | 无有效参数 | - | - | - | - | 0 | - |\n"
            continue
        md_content += (
            f"| {fname} | {p['ma_win']} | {p['entry_thres']:.3f} | {p['exit_thres']:.3f} "
            f"| {res['total_return']:.2%} | {res['win_rate']:.2%} | {res['trade_count']} | {res['final_asset']} |\n"
        )
        if res["total_return"] > global_best_ret:
            global_best_ret = res["total_return"]
            global_best_item = item

    # 全局最优标的
    md_content += "\n## 三、全局最优表现标的\n"
    if global_best_item:
        gb_fname = global_best_item["file_name"]
        gb_p = global_best_item["best_param"]
        gb_res = global_best_item["result"]
        md_content += f"- 最优数据文件：`{gb_fname}`\n"
        md_content += f"- 最优适配参数：均线{gb_p['ma_win']}日，开仓偏离{gb_p['entry_thres']}，平仓偏离{gb_p['exit_thres']}\n"
        md_content += f"- 该标的最高收益率：{gb_res['total_return']:.2%}，胜率：{gb_res['win_rate']:.2%}\n\n"
    else:
        md_content += "- 暂无有效盈利回测结果\n\n"

    # 策略总结
    md_content += "## 四、策略总结与优化建议\n"
    md_content += "1. 本策略依靠价格偏离短期均线程度判定回归机会，震荡行情表现更佳，趋势单边行情易连续止损\n"
    md_content += "2. 可增加趋势过滤指标（如大周期均线方向），只在震荡区间开仓\n"
    md_content += "3. 可动态调整偏离阈值，波动率放大时放宽开仓条件\n"
    md_content += "4. 实盘建议降低单次仓位，叠加资金费率、持仓情绪数据二次过滤信号\n"

    return md_content

def main():
    # 1. 删除旧报告
    del_old_report()
    # 2. 获取所有CSV
    csv_files = get_all_csv_files(DATA_DIR)
    if not csv_files:
        print("data目录下未找到任何CSV行情文件！")
        return
    print(f"发现待回测CSV文件总数：{len(csv_files)}")

    all_backtest_result = []
    # 3. 逐个文件独立回测
    for item in csv_files:
        fn = item["file_name"]
        fp = item["file_path"]
        print(f"\n===== 开始回测：{fn} =====")
        try:
            df = load_single_csv(fp)
            best_p, best_r = grid_search_best_params(df)
            all_backtest_result.append({
                "file_name": fn,
                "file_path": fp,
                "best_param": best_p,
                "result": best_r if best_r else {"total_return":0,"win_rate":0,"trade_count":0,"final_asset":INIT_CAPITAL,"trade_list":[]}
            })
            if best_p:
                print(f"完成 {fn} | 最优收益：{best_r['total_return']:.2%}")
            else:
                print(f"{fn} 无有效交易信号")
        except Exception as e:
            print(f"回测 {fn} 出错：{str(e)}")
            all_backtest_result.append({
                "file_name": fn,
                "file_path": fp,
                "best_param": None,
                "result": {"total_return":0,"win_rate":0,"trade_count":0,"final_asset":INIT_CAPITAL,"trade_list":[]}
            })

    # 4. 生成MD报告并写入data目录
    md_text = generate_markdown_report(all_backtest_result)
    with open(REPORT_SAVE_PATH, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"\n🎉 全部回测完成！综合报告已生成至：{REPORT_SAVE_PATH}")

if __name__ == "__main__":
    main()
