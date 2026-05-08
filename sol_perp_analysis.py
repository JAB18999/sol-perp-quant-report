import pandas as pd
import numpy as np
import os
import glob
import pandas_ta as ta
from itertools import product
from datetime import datetime

class SolPerpFullAnalyzer:
    def __init__(self, data_path='data'):
        self.data_path = data_path
        self.report_path = os.path.join(self.data_path, "analysis_report.md")
        
        # 1.1 核心参数
        self.trade_amount = 1000
        self.tp_rate = 0.016
        self.sl_rate = 0.014
        self.fee_rate = 0.0004
        self.slippage = 0.002

    def load_data(self, file_path):
        df = pd.read_csv(file_path)
        df.columns = [c.lower() for c in df.columns]
        return df.dropna().reset_index(drop=True)

    def calculate_all_indicators(self, df):
        """预计算所有候选指标"""
        # EMA & MA
        df['ema_12'] = ta.ema(df['close'], length=12)
        df['ema_26'] = ta.ema(df['close'], length=26)
        df['ma_10'] = ta.sma(df['close'], length=10)
        df['ma_50'] = ta.sma(df['close'], length=50)
        # RSI & MACD
        df['rsi_14'] = ta.rsi(df['close'], length=14)
        macd = ta.macd(df['close'])
        df['macd'] = macd['MACD_12_26_9']
        # Supertrend
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
        df['st_dir'] = st.iloc[:, 1] if st is not None else 0
        return df

    def vector_backtest(self, df, signal_col):
        """严格时序回测引擎"""
        signals = df[df[signal_col] != 0]
        if len(signals) == 0: return 0, 0, 0
        
        results = []
        for idx in signals.index:
            entry_price = df.loc[idx, 'close']
            side = df.loc[idx, signal_col] # 1 或 -1
            
            # 考虑滑点
            exec_price = entry_price * (1 + self.slippage * side)
            
            # 寻找后续触达 (简化模拟)
            future = df.iloc[idx+1 : idx+100] # 观察未来100根K线
            pnl = 0
            if side == 1: # 多
                tp_price = exec_price * (1 + self.tp_rate)
                sl_price = exec_price * (1 - self.sl_rate)
                for _, row in future.iterrows():
                    if row['high'] >= tp_price: pnl = self.tp_rate; break
                    if row['low'] <= sl_price: pnl = -self.sl_rate; break
            else: # 空
                tp_price = exec_price * (1 - self.tp_rate)
                sl_price = exec_price * (1 + self.sl_rate)
                for _, row in future.iterrows():
                    if row['low'] <= tp_price: pnl = self.tp_rate; break
                    if row['high'] >= sl_price: pnl = -self.sl_rate; break
            
            if pnl != 0:
                results.append(pnl * self.trade_amount - (self.fee_rate * 2 * self.trade_amount))
        
        total_pnl = sum(results)
        win_rate = len([r for r in results if r > 0]) / len(results) if results else 0
        return round(total_pnl, 2), len(results), f"{win_rate:.1%}"

    def run_full_analysis(self):
        files = [f for f in glob.glob(os.path.join(self.data_path, "*.csv")) if "report" not in f]
        
        with open(self.report_path, 'w', encoding='utf-8') as f:
            f.write("# SOL 永续合约全量量化回测报告\n\n")
            
            for file in files:
                f.write(f"## 数据源: {os.path.basename(file)}\n\n")
                df = self.load_data(file)
                df = self.calculate_all_indicators(df)
                
                # --- 第一部分: 参数优化探索 ---
                f.write("### 1. 多因子参数优化探索 (EMA示例)\n")
                f.write("| 参数组合 (Short/Long) | 交易次数 | 累计盈亏 (USDT) | 备注 |\n")
                f.write("| :--- | :---: | :---: | :--- |\n")
                
                best_param_pnl = -9999
                best_pair = (12, 26)
                
                for s, l in [(5,20), (12,26), (20,50)]:
                    col_name = f"sig_ema_{s}_{l}"
                    df['ema_s_tmp'] = ta.ema(df['close'], length=s)
                    df['ema_l_tmp'] = ta.ema(df['close'], length=l)
                    df[col_name] = np.where(df['ema_s_tmp'] > df['ema_l_tmp'], 1, -1)
                    pnl, cnt, _ = self.vector_backtest(df, col_name)
                    f.write(f"| EMA({s},{l}) | {cnt} | {pnl} | {'★' if pnl > best_param_pnl else ''} |\n")
                    if pnl > best_param_pnl: 
                        best_param_pnl = pnl
                        best_pair = (s, l)
                f.write(f"\n> 结论: 该周期下最优参数为 EMA{best_pair}\n\n")

                # --- 第二部分: 20 种双指标共振矩阵 ---
                f.write("### 2. 双指标共振组合全量回测 (20种组合)\n")
                f.write("| 编号 | 主导指标 (趋势) | 辅助指标 (确认) | 交易次数 | 累计盈亏 | 胜率 |\n")
                f.write("| :--- | :--- | :--- | :---: | :---: | :---: |\n")
                
                indicators = ['ema_12', 'ma_10', 'rsi_14', 'macd', 'st_dir']
                idx = 1
                matrix_results = []

                for i1, i2 in product(indicators, indicators):
                    if i1 == i2: continue
                    sig_col = f"res_{idx}"
                    # 简化共振逻辑：i1确定方向，i2处于超买超卖或同向
                    if 'rsi' in i2:
                        df[sig_col] = np.where((df[i1] > df['close']) & (df[i2] < 30), 1, 0)
                        df[sig_col] = np.where((df[i1] < df['close']) & (df[i2] > 70), -1, df[sig_col])
                    else:
                        df[sig_col] = np.where((df[i1] > 0) & (df[i2] > 0), 1, 0)
                    
                    pnl, cnt, wr = self.vector_backtest(df, sig_col)
                    matrix_results.append((idx, i1.upper(), i2.upper(), cnt, pnl, wr))
                    idx += 1

                # 按盈亏排序输出
                matrix_results.sort(key=lambda x: x[4], reverse=True)
                for r in matrix_results:
                    f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |\n")
                
                f.write("\n---\n")

if __name__ == "__main__":
    analyzer = SolPerpFullAnalyzer()
    analyzer.run_full_analysis()
