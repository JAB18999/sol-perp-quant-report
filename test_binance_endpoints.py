#!/usr/bin/env python3
"""
Binance 交易所 API 端点连通性测试脚本
用于测试 Binance 官方所有可用备用域名

使用方法:
    python test_binance_endpoints.py

输出:
    - 每个端点的延迟
    - 数据获取是否成功
    - 最优推荐端点
"""

import asyncio
import ccxt
import time
import json
from datetime import datetime
from typing import Dict, List, Optional

# ============================================
# Binance 官方端点配置
# ============================================
# 官方文档: https://developers.binance.com/docs/genesis

BINANCE_ENDPOINTS = {
    # ---- 现货 API (币币交易) ----
    "Binance 现货-主域名 (api.binance.com)": {
        "baseUrl": "https://api.binance.com",
        "type": "spot",
        "path": "/api/v3/ping",
    },
    "Binance 现货-CDN1 (api1.binance.com)": {
        "baseUrl": "https://api1.binance.com",
        "type": "spot",
        "path": "/api/v3/ping",
    },
    "Binance 现货-CDN2 (api2.binance.com)": {
        "baseUrl": "https://api2.binance.com",
        "type": "spot",
        "path": "/api/v3/ping",
    },
    "Binance 现货-CDN3 (api3.binance.com)": {
        "baseUrl": "https://api3.binance.com",
        "type": "spot",
        "path": "/api/v3/ping",
    },
    "Binance 现货-CDN4 (api4.binance.com)": {
        "baseUrl": "https://api4.binance.com",
        "type": "spot",
        "path": "/api/v3/ping",
    },
    
    # ---- USDT 永续合约 API ----
    "Binance 合约-USDT主域名 (fapi.binance.com)": {
        "baseUrl": "https://fapi.binance.com",
        "type": "future",
        "path": "/fapi/v1/ping",
    },
    "Binance 合约-USDT-CDN1 (fapi1.binance.com)": {
        "baseUrl": "https://fapi1.binance.com",
        "type": "future",
        "path": "/fapi/v1/ping",
    },
    "Binance 合约-USDT-CDN2 (fapi2.binance.com)": {
        "baseUrl": "https://fapi2.binance.com",
        "type": "future",
        "path": "/fapi/v1/ping",
    },
    "Binance 合约-USDT-CDN3 (fapi3.binance.com)": {
        "baseUrl": "https://fapi3.binance.com",
        "type": "future",
        "path": "/fapi/v1/ping",
    },
    "Binance 合约-USDT-CDN4 (fapi4.binance.com)": {
        "baseUrl": "https://fapi4.binance.com",
        "type": "future",
        "path": "/fapi/v1/ping",
    },
    
    # ---- Coin-M 永续合约 API ----
    "Binance 合约-COIN主域名 (dapi.binance.com)": {
        "baseUrl": "https://dapi.binance.com",
        "type": "delivery",
        "path": "/dapi/v1/ping",
    },
    "Binance 合约-COIN-CDN1 (dapi1.binance.com)": {
        "baseUrl": "https://dapi1.binance.com",
        "type": "delivery",
        "path": "/dapi/v1/ping",
    },
    "Binance 合约-COIN-CDN2 (dapi2.binance.com)": {
        "baseUrl": "https://dapi2.binance.com",
        "type": "delivery",
        "path": "/dapi/v1/ping",
    },
    "Binance 合约-COIN-CDN3 (dapi3.binance.com)": {
        "baseUrl": "https://dapi3.binance.com",
        "type": "delivery",
        "path": "/dapi/v1/ping",
    },
    
    # ---- 备用/镜像站点 ----
    "Binance 现货-镜像1 (binance.me)": {
        "baseUrl": "https://binance.me",
        "type": "spot",
        "path": "/api/v3/ping",
    },
    "Binance 现货-镜像2 (binance.info)": {
        "baseUrl": "https://binance.info",
        "type": "spot",
        "path": "/api/v3/ping",
    },
    "Binance 现货-备用 (binance.com.uk)": {
        "baseUrl": "https://www.binance.com.uk",
        "type": "spot",
        "path": "/api/v3/ping",
    },
}

# 测试参数
TEST_SYMBOL = "SOL/USDT"
TEST_TIMEFRAME = "1h"
TEST_LIMIT = 5


class BinanceEndpointTester:
    def __init__(self):
        self.results: List[Dict] = []
        
    def test_http_connectivity(self, name: str, base_url: str, path: str = "/api/v3/ping") -> Dict:
        """使用 HTTP HEAD 测试端点连通性"""
        import urllib.request
        import urllib.error
        
        result = {
            "name": name,
            "base_url": base_url,
            "status": "❌ 失败",
            "http_code": None,
            "ping_ms": None,
            "error": None,
        }
        
        url = base_url + path
        start = time.time()
        
        try:
            req = urllib.request.Request(url, method='HEAD')
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=5) as response:
                result["http_code"] = response.status
                result["ping_ms"] = round((time.time() - start) * 1000, 2)
                result["status"] = "✅ 可达"
        except urllib.error.HTTPError as e:
            result["http_code"] = e.code
            result["error"] = f"HTTP {e.code}"
            if e.code == 451:
                result["error"] = "HTTP 451 (地区限制)"
        except urllib.error.URLError as e:
            result["error"] = f"连接失败: {str(e.reason)}"
        except Exception as e:
            result["error"] = f"错误: {str(e)[:30]}"
        
        return result
    
    async def test_with_ccxt(self, name: str, config: Dict) -> Dict:
        """使用 ccxt 测试完整的数据获取"""
        result = {
            "name": name,
            "base_url": config["baseUrl"],
            "type": config["type"],
            "status": "❌ 失败",
            "ping_ms": None,
            "fetch_ms": None,
            "has_data": False,
            "last_candle": None,
            "error": None,
        }
        
        try:
            exchange_config = {
                'enableRateLimit': True,
                'options': {
                    'defaultType': config["type"],
                    'baseUrl': config["baseUrl"],
                }
            }
            
            exchange = getattr(ccxt, 'binance')(exchange_config)
            
            # 1. 加载市场数据测试连通性
            start = time.time()
            await asyncio.to_thread(exchange.loadMarkets)
            load_ms = (time.time() - start) * 1000
            result["ping_ms"] = round(load_ms, 2)
            
            # 2. 测试获取 K 线数据
            start = time.time()
            ohlcv = await asyncio.to_thread(
                exchange.fetch_ohlcv, TEST_SYMBOL, TEST_TIMEFRAME, {'limit': TEST_LIMIT}
            )
            fetch_ms = (time.time() - start) * 1000
            result["fetch_ms"] = round(fetch_ms, 2)
            
            if ohlcv and len(ohlcv) > 0:
                result["has_data"] = True
                result["status"] = "✅ 成功"
                last = ohlcv[-1]
                dt = datetime.fromtimestamp(last[0] / 1000)
                result["last_candle"] = f"{dt.strftime('%Y-%m-%d %H:%M')} | O:{last[1]:.2f} H:{last[2]:.2f} L:{last[3]:.2f} C:{last[4]:.2f}"
            else:
                result["error"] = "无数据"
                
        except ccxt.NetworkError as e:
            result["error"] = f"网络错误: {str(e)[:40]}"
        except ccxt.ExchangeError as e:
            result["error"] = f"交易所错误: {str(e)[:40]}"
        except Exception as e:
            result["error"] = f"未知错误: {str(e)[:40]}"
        
        await asyncio.sleep(0.3)  # 避免请求过快
        return result
    
    async def run_tests(self):
        """运行所有测试"""
        print("=" * 90)
        print("🧪 Binance 交易所 API 端点连通性测试")
        print("=" * 90)
        print(f"📊 测试品种: {TEST_SYMBOL} | 周期: {TEST_TIMEFRAME} | 数据条数: {TEST_LIMIT}")
        print(f"🕐 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 90)
        
        # 第一阶段: HTTP 连通性测试
        print("\n📡 第一阶段: HTTP 端点连通性测试...")
        http_results = []
        for name, config in BINANCE_ENDPOINTS.items():
            print(f"  ⏳ {name}...", end=" ", flush=True)
            r = self.test_http_connectivity(name, config["baseUrl"], config["path"])
            http_results.append(r)
            if r["status"] == "✅ 可达":
                print(f"✅ {r['http_code']} ({r['ping_ms']}ms)")
            elif r["http_code"]:
                print(f"⚠️ HTTP {r['http_code']}")
            else:
                print(f"❌ {r['error']}")
        
        # 找出可达的端点
        reachable = [r for r in http_results if r["status"] == "✅ 可达"]
        print(f"\n📊 HTTP 测试结果: {len(reachable)}/{len(http_results)} 端点可达")
        
        # 第二阶段: ccxt 数据获取测试
        print("\n📡 第二阶段: ccxt 数据获取测试...")
        ccxt_results = []
        
        for r in http_results:
            if r["status"] != "✅ 可达":
                continue
                
            # 找出对应的配置
            config = None
            for name, cfg in BINANCE_ENDPOINTS.items():
                if cfg["baseUrl"] == r["base_url"]:
                    config = cfg
                    break
            
            if not config:
                continue
                
            print(f"  ⏳ {r['name']}...", end=" ", flush=True)
            cr = await self.test_with_ccxt(r['name'], config)
            ccxt_results.append(cr)
            
            if cr["status"] == "✅ 成功":
                print(f"✅ 加载:{cr['ping_ms']}ms 获取:{cr['fetch_ms']}ms")
            else:
                print(f"❌ {cr['error']}")
        
        return http_results, ccxt_results
    
    def print_summary(self, http_results: List[Dict], ccxt_results: List[Dict]):
        """打印测试汇总"""
        print("\n" + "=" * 90)
        print("📋 测试结果汇总")
        print("=" * 90)
        
        # HTTP 测试汇总
        http_success = [r for r in http_results if r["status"] == "✅ 可达"]
        print(f"\n🌐 HTTP 连通性: {len(http_success)}/{len(http_results)} 端点可达")
        
        # ccxt 测试汇总
        if ccxt_results:
            ccxt_success = [r for r in ccxt_results if r["has_data"]]
            print(f"📊 数据获取: {len(ccxt_success)}/{len(ccxt_results)} 端点成功")
            
            if ccxt_success:
                # 按总响应时间排序
                sorted_results = sorted(ccxt_success, key=lambda x: (x["ping_ms"] or 9999) + (x["fetch_ms"] or 9999))
                
                print("\n🏆 端点性能排名 (按响应速度):")
                for i, r in enumerate(sorted_results, 1):
                    total_ms = (r["ping_ms"] or 0) + (r["fetch_ms"] or 0)
                    print(f"  {i}. {r['name']}")
                    print(f"     - 加载延迟: {r['ping_ms']}ms")
                    print(f"     - 获取延迟: {r['fetch_ms']}ms")
                    print(f"     - 最新数据: {r['last_candle']}")
                
                # 推荐端点
                best = sorted_results[0]
                print(f"\n✅ 推荐端点: {best['name']}")
                print(f"   baseUrl: {best['base_url']}")
                print(f"   类型: {best['type']}")
                print(f"   总延迟: {(best['ping_ms'] or 0) + (best['fetch_ms'] or 0)}ms")
                
                # 生成代码片段
                print("\n📝 使用示例 (ccxt):")
                print("```python")
                print(f"exchange = ccxt.binance({{")
                print(f"    'enableRateLimit': True,")
                print(f"    'options': {{")
                print(f"        'defaultType': '{best['type']}',")
                print(f"        'baseUrl': '{best['base_url']}',")
                print(f"    }}")
                print(f"}})")
                print("```")
        else:
            print("\n⚠️ 所有端点均无法通过 ccxt 获取数据")
            print("可能原因:")
            print("  1. 地区网络限制 (返回 HTTP 451)")
            print("  2. API 密钥缺失 (需要添加 'options': {'defaultType': 'swap'})")
            print("  3. 需要使用代理/VPN")
        
        # 失败原因分析
        failed = [r for r in http_results if r["status"] != "✅ 可达"]
        if failed:
            print(f"\n❌ 不可达端点 ({len(failed)}):")
            for r in failed[:5]:  # 只显示前5个
                print(f"  • {r['name']}: {r['error'] or f'HTTP {r[\"http_code\"]}'}")


async def main():
    tester = BinanceEndpointTester()
    http_results, ccxt_results = await tester.run_tests()
    tester.print_summary(http_results, ccxt_results)


if __name__ == "__main__":
    asyncio.run(main())
