import pandas as pd
import numpy as np
import os
import glob
import pandas_ta as ta
from datetime import datetime

class SolPerpQuantAnalyzer:
    def __init__(self, data_path='data'):
        self.data_path = data_path
        self.report_name = "analysis_report.md"
        self.report_path = os.path.join(self.data_path, self.report_name)
        
        # 报告 1.1 核心参数设定 
        self.tp_rate = 0.016      # 止盈 1.6% 
        self.sl_rate = 0.014      # 止损 1.4% 
        self.fee_rate = 0.0004    # 手续费 0.04% 
        self.slippage = 0.002     # 滑点 0.2% 
        self.trade_amount = 1000  # 单笔 1000 USDT 

    def clean_old_report(self):
        """运行前自动删除上一次的报告文件"""
        if os.path.exists(self.report_path):
            os.remove(self.report_path)
            print(f"已清理旧报告: {self.report_path}")

    def load_data(self, file_name):
        df = pd.read_csv(file_name)
        df.columns = [c.lower() for c in df.columns]
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df.sort_values('timestamp') if 'timestamp' in df.columns else df

    def calculate_indicators(self, df):
        """计算报告 2.2.2 提到的基础指标 [cite: 47-53]"""
        df['ema_12'] = ta.ema(df['close'], length=12) # [cite: 49]
        df['ema_26'] = ta.ema(df['close'], length=26) # [cite: 49]
        df['ma_10'] = ta.sma(df['close'], length=10)   # [cite: 50]
        df['ma_50'] = ta.sma(df['close'], length=50)   # [cite: 50]
        df['rsi_14'] = ta.rsi(df['close'], length=14)  # [cite: 51]
        
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9) # [cite: 52]
        df = pd.concat([df, macd], axis=1)
        
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3) # [cite: 53]
        if st is not None:
            df['st_dir'] = st.iloc[:, 1]
        return df

    def run_resonance_backtest(self, df):
        """执行状态过滤+触发确认逻辑 [cite: 59-67]"""
        df['signal'] = 0
        # 状态过滤：EMA 多头 [cite: 61] + 触发确认：RSI 低位 [cite: 62]
        long_cond = (df['ema_12'] > df['ema_26']) & (df['rsi_14'] < 35)
        short_cond = (df['ema_12'] < df['ema_26']) & (df['rsi_14'] > 65)
        
        df.loc[long_cond, 'signal'] = 1
        df.loc[short_cond, 'signal'] = -1
        
        trades = df[df['signal'] != 0]
        count = len(trades)
        win_rate = 0.42 # 模拟胜率
        
        # 盈亏比计算 1.6 / 1.4 = 1.14 
        profit = count * (win_rate * self.tp_rate - (1-win_rate) * self.sl_rate) * self.trade_amount
        
        return {
            "数据源": "", 
            "交易总数": count,
            "预估盈亏(USDT)": f"{profit:.2f}",
            "假设胜率": f"{win_rate*100}%",
            "盈亏比": "1.14:1"
        }

    def generate_md_report(self, results):
        """生成 Markdown 格式报告文件"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.report_path, 'w', encoding='utf-8') as f:
            f.write(f"# SOL 永续合约量化分析自动报告\n\n")
            f.write(f"- **生成时间**: {now}\n")
            f.write(f"- **止盈比例**: {self.tp_rate*100}%\n")
            f.write(f"- **止损比例**: {self.sl_rate*100}%\n")
            f.write(f"- **单笔金额**: {self.trade_amount} USDT\n\n")
            f.write("## 绩效汇总表\n\n")
            
            # 构建 Markdown 表格
            header = "| 数据源 | 交易总数 | 预估盈亏(USDT) | 假设胜率 | 盈亏比 |\n"
            separator = "| :--- | :---: | :---: | :---: | :---: |\n"
            f.write(header + separator)
            
            for res in results:
                row = f"| {res['数据源']} | {res['交易总数']} | {res['预估盈亏(USDT)']} | {res['假设胜率']} | {res['盈亏比']} |\n"
                f.write(row)
            
            f.write("\n\n> 注意：本报告由脚本自动生成，回测结果仅供参考。")

    def analyze_all(self):
        self.clean_old_report()
        csv_files = [f for f in glob.glob(os.path.join(self.data_path, "*.csv")) 
                     if os.path.basename(f) != self.report_name]
        
        all_results = []
        for file in csv_files:
            print(f"分析中: {file}")
            df = self.load_data(file)
            df = self.calculate_indicators(df)
            res = self.run_resonance_backtest(df)
            res['数据源'] = os.path.basename(file)
            all_results.append(res)
        
        if all_results:
            self.generate_md_report(all_results)
            print(f"报告生成成功: {self.report_path}")
        else:
            print("未发现数据文件。")

if __name__ == "__main__":
    analyzer = SolPerpQuantAnalyzer()
    analyzer.analyze_all()
