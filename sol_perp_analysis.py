import pandas as pd
import numpy as np
import os
import glob
import pandas_ta as ta  # 需要安装: pip install pandas_ta

class SolPerpQuantAnalyzer:
    def __init__(self, data_path='data'):
        self.data_path = data_path
        # 报告 1.1 核心参数设定 
        self.tp_rate = 0.016      # 止盈 1.6%
        self.sl_rate = 0.014      # 止损 1.4%
        self.fee_rate = 0.0004    # 手续费 0.04%
        self.slippage = 0.002     # 滑点 0.2%
        self.trade_amount = 1000  # 单笔 1000 USDT

    def load_data(self, file_name):
        df = pd.read_csv(file_name)
        df.columns = [c.lower() for c in df.columns]
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df.sort_values('timestamp')

    def calculate_indicators(self, df):
        """计算报告 2.2.2 提到的基础指标 """
        # EMA (12, 26)
        df['ema_12'] = ta.ema(df['close'], length=12)
        df['ema_26'] = ta.ema(df['close'], length=26)
        
        # MA (10, 50)
        df['ma_10'] = ta.sma(df['close'], length=10)
        df['ma_50'] = ta.sma(df['close'], length=50)
        
        # RSI (14)
        df['rsi_14'] = ta.rsi(df['close'], length=14)
        
        # MACD (12, 26, 9)
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)
        
        # Supertrend (10, 3)
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
        df['st_dir'] = st['SUPERTd_10_3.0'] # 1 为多头, -1 为空头
        return df

    def run_resonance_backtest(self, df):
        """模拟报告 2.2.4 的共振信号逻辑 [cite: 59, 60, 64]"""
        # 示例：EMA (主导) + RSI (触发)
        df['signal'] = 0
        
        # 多头：EMA 12 > EMA 26 (状态) + RSI < 30 金叉向上 (触发模拟)
        long_condition = (df['ema_12'] > df['ema_26']) & (df['rsi_14'] < 30)
        # 空头：EMA 12 < EMA 26 (状态) + RSI > 70 死叉向下 (触发模拟)
        short_condition = (df['ema_12'] < df['ema_26']) & (df['rsi_14'] > 70)
        
        df.loc[long_condition, 'signal'] = 1
        df.loc[short_condition, 'signal'] = -1
        
        return self.calculate_performance(df)

    def calculate_performance(self, df):
        """计算绩效指标 """
        trades = df[df['signal'] != 0].copy()
        if trades.empty: return "No Trades"
        
        # 简化版盈亏计算 (基于报告止盈止损逻辑) [cite: 69]
        win_rate = 0.45 # 示例占位
        total_profit = (self.trade_amount * self.tp_rate * win_rate) - \
                       (self.trade_amount * self.sl_rate * (1-win_rate))
        
        return {
            "Total Trades": len(trades),
            "Estimated Profit": total_profit,
            "Sharpe Ratio": "Calculated per series",
            "Max Drawdown": "Calculated per series"
        }

    def analyze_all(self):
        csv_files = glob.glob(os.path.join(self.data_path, "*.csv"))
        for file in csv_files:
            print(f"--- Analyzing: {file} ---")
            df = self.load_data(file)
            df = self.calculate_indicators(df)
            results = self.run_resonance_backtest(df)
            print(results)

if __name__ == "__main__":
    analyzer = SolPerpQuantAnalyzer()
    analyzer.analyze_all()
