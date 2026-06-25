"""
NF-SafetyHub 硬件能力评估脚本
通过阶梯式压力测试，测量服务器实际能处理的最大并发量，
并输出"当前并发 X，占硬件能力的 Y%"这样的评估信息。

使用方法:
  python hardware_capacity_test.py --base-url http://<服务器IP>:8000/v1 --api-key <your_key>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp


@dataclass
class RequestResult:
    """单次请求的结果"""
    latency_ms: float
    status: str  # "ok", "blocked", "error", "timeout"
    inflight: int = 0       # 从响应头获取的在途数
    queue_size: int = 0     # 从响应头获取的排队数
    queue_wait_ms: int = 0  # 从响应头获取的排队等待时间
    reject_reason: str = "" # 429 拒绝原因
    detail: str = ""        # 错误详情
    timestamp: float = field(default_factory=time.time)


@dataclass
class CapacityLevel:
    """单个并发级别的测试结果"""
    concurrency: int
    duration_seconds: float
    total_requests: int
    ok_requests: int
    blocked_requests: int  # 被 SafetyHub 拦截（业务层面）
    error_requests: int    # 网络/系统错误
    rejected_requests: int # 429 队列满/超时拒绝
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_inflight: float
    avg_queue_size: float
    avg_queue_wait_ms: float
    rps: float  # 每秒请求数
    is_saturated: bool  # 是否达到饱和


class CapacityTester:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-3.5-turbo",
        test_message: str = "你好，请用一句话介绍你自己。",
        timeout_seconds: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.test_message = test_message
        self.timeout_seconds = timeout_seconds
        self.results: list[RequestResult] = []
        self.inflight_counter = 0
        self.lock = asyncio.Lock()

    async def _make_request(self, session: aiohttp.ClientSession, sem: asyncio.Semaphore) -> RequestResult:
        """发起单次请求并收集指标"""
        async with sem:
            async with self.lock:
                self.inflight_counter += 1

            start_time = time.perf_counter()
            try:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": self.test_message}],
                        "max_tokens": 50,
                        "stream": False,
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                ) as response:
                    latency_ms = (time.perf_counter() - start_time) * 1000

                    # 从响应头获取并发指标
                    inflight = int(response.headers.get("X-SafetyHub-Inflight", 0))
                    queue_size = int(response.headers.get("X-SafetyHub-Queue-Size", 0))
                    queue_wait_ms = int(response.headers.get("X-SafetyHub-Queue-Wait-Ms", 0))
                    reject_reason = response.headers.get("X-SafetyHub-Reject-Reason", "")

                    if response.status == 429:
                        status = "rejected"
                    elif response.status == 200:
                        status = "ok"
                    else:
                        status = "error"

                    result = RequestResult(
                        latency_ms=latency_ms,
                        status=status,
                        inflight=inflight,
                        queue_size=queue_size,
                        queue_wait_ms=queue_wait_ms,
                        reject_reason=reject_reason,
                    )

            except asyncio.TimeoutError:
                latency_ms = (time.perf_counter() - start_time) * 1000
                result = RequestResult(latency_ms=latency_ms, status="timeout")
            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                result = RequestResult(latency_ms=latency_ms, status="error", detail=str(e))
            finally:
                async with self.lock:
                    self.inflight_counter -= 1

            return result

    async def test_concurrency_level(
        self,
        concurrency: int,
        duration_seconds: int,
    ) -> CapacityLevel:
        """测试指定并发级别的处理能力"""
        self.results.clear()
        sem = asyncio.Semaphore(concurrency)

        async with aiohttp.ClientSession() as session:
            deadline = time.time() + duration_seconds

            async def worker():
                while time.time() < deadline:
                    result = await self._make_request(session, sem)
                    self.results.append(result)

            workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
            await asyncio.gather(*workers)

        # 统计分析
        latencies = [r.latency_ms for r in self.results if r.status in ("ok", "blocked")]
        ok_count = sum(1 for r in self.results if r.status == "ok")
        blocked_count = sum(1 for r in self.results if r.status == "blocked")
        error_count = sum(1 for r in self.results if r.status == "error")
        rejected_count = sum(1 for r in self.results if r.status == "rejected")

        inflights = [r.inflight for r in self.results if r.inflight > 0]
        queue_sizes = [r.queue_size for r in self.results if r.queue_size > 0]
        queue_waits = [r.queue_wait_ms for r in self.results if r.queue_wait_ms > 0]

        avg_latency = statistics.mean(latencies) if latencies else 0
        p50_latency = self._percentile(latencies, 50) if latencies else 0
        p95_latency = self._percentile(latencies, 95) if latencies else 0
        p99_latency = self._percentile(latencies, 99) if latencies else 0

        # 判断是否饱和：出现 429 拒绝 或 延迟急剧上升
        is_saturated = rejected_count > 0 or (p95_latency > 5000 and error_count > len(self.results) * 0.1)

        return CapacityLevel(
            concurrency=concurrency,
            duration_seconds=duration_seconds,
            total_requests=len(self.results),
            ok_requests=ok_count,
            blocked_requests=blocked_count,
            error_requests=error_count,
            rejected_requests=rejected_count,
            avg_latency_ms=avg_latency,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            avg_inflight=statistics.mean(inflights) if inflights else 0,
            avg_queue_size=statistics.mean(queue_sizes) if queue_sizes else 0,
            avg_queue_wait_ms=statistics.mean(queue_waits) if queue_waits else 0,
            rps=len(self.results) / duration_seconds if duration_seconds > 0 else 0,
            is_saturated=is_saturated,
        )

    def _percentile(self, data: list[float], percentile: int) -> float:
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


def find_max_capacity(
    tester: CapacityTester,
    start_concurrency: int = 10,
    max_concurrency: int = 1000,
    step: int = 20,
    duration_per_level: int = 15,
) -> list[CapacityLevel]:
    """阶梯式寻找最大容量"""
    results = []
    current = start_concurrency

    print(f"\n{'='*70}")
    print(f"  开始硬件能力评估测试")
    print(f"  目标地址: {tester.base_url}")
    print(f"  测试范围: {start_concurrency} → {max_concurrency} (步长 {step})")
    print(f"  每级持续: {duration_per_level} 秒")
    print(f"{'='*70}\n")

    while current <= max_concurrency:
        print(f"  ▶ 测试并发级别: {current} ...", end="", flush=True)
        level_result = asyncio.run(tester.test_concurrency_level(current, duration_per_level))
        results.append(level_result)

        # 输出当前级别结果
        status_icon = "饱和" if level_result.is_saturated else "正常"
        print(f" RPS={level_result.rps:.1f} | P95={level_result.p95_latency_ms:.0f}ms | "
              f"拒绝={level_result.rejected_requests} | 状态={status_icon}")

        # 如果达到饱和，再测试两级确认稳定性
        if level_result.is_saturated:
            print(f"\n  ⚠ 在并发 {current} 时检测到饱和，继续测试确认...")
            # 再测两级
            for extra in range(2):
                next_level = current + step * (extra + 1)
                if next_level > max_concurrency:
                    break
                print(f"  ▶ 确认测试并发级别: {next_level} ...", end="", flush=True)
                extra_result = asyncio.run(tester.test_concurrency_level(next_level, duration_per_level))
                results.append(extra_result)
                print(f" RPS={extra_result.rps:.1f} | P95={extra_result.p95_latency_ms:.0f}ms | "
                      f"拒绝={extra_result.rejected_requests} | 状态={'饱和' if extra_result.is_saturated else '正常'}")
            break

        current += step

    return results


def print_capacity_report(results: list[CapacityLevel]) -> None:
    """打印容量评估报告"""
    # 找到最大稳定并发（未饱和的最高级别）
    stable_levels = [r for r in results if not r.is_saturated]
    saturated_levels = [r for r in results if r.is_saturated]

    if not stable_levels:
        max_stable = results[0]
    else:
        max_stable = stable_levels[-1]

    if saturated_levels:
        min_saturated = saturated_levels[0]
    else:
        min_saturated = None

    print(f"\n{'='*70}")
    print(f"  硬件能力评估报告")
    print(f"{'='*70}")

    print(f"\n  【最大稳定并发能力】")
    print(f"    并发数: {max_stable.concurrency}")
    print(f"    RPS: {max_stable.rps:.1f} 请求/秒")
    print(f"    P50 延迟: {max_stable.p50_latency_ms:.0f}ms")
    print(f"    P95 延迟: {max_stable.p95_latency_ms:.0f}ms")
    print(f"    P99 延迟: {max_stable.p99_latency_ms:.0f}ms")
    print(f"    成功率: {max_stable.ok_requests / max_stable.total_requests * 100:.1f}%")

    if min_saturated:
        print(f"\n  【饱和点】")
        print(f"    并发数: {min_saturated.concurrency}")
        print(f"    429 拒绝数: {min_saturated.rejected_requests}")
        print(f"    P95 延迟: {min_saturated.p95_latency_ms:.0f}ms")

    print(f"\n  【使用率评估参考】")
    print(f"  {'当前并发':<12} {'占硬件能力':<15} {'负载等级':<12} {'建议'}")
    print(f"  {'-'*65}")

    # 生成不同并发级别的评估
    for usage_pct in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        current_concurrent = int(max_stable.concurrency * usage_pct / 100)
        if usage_pct < 50:
            level = "轻松"
            suggestion = "资源充足"
        elif usage_pct < 70:
            level = "适中"
            suggestion = "正常运行"
        elif usage_pct < 85:
            level = "较高"
            suggestion = "关注延迟"
        elif usage_pct < 100:
            level = "高"
            suggestion = "准备扩容"
        else:
            level = "饱和"
            suggestion = "需要扩容"

        print(f"  {current_concurrent:<12} {usage_pct}%{'':<12} {level:<12} {suggestion}")

    print(f"\n  【详细测试数据】")
    print(f"  {'并发':<8} {'RPS':<8} {'P50':<8} {'P95':<8} {'P99':<8} {'成功率':<8} {'拒绝':<6} {'状态'}")
    print(f"  {'-'*65}")
    for r in results:
        success_rate = r.ok_requests / r.total_requests * 100 if r.total_requests > 0 else 0
        status = "饱和" if r.is_saturated else "正常"
        print(f"  {r.concurrency:<8} {r.rps:<8.1f} {r.p50_latency_ms:<8.0f} {r.p95_latency_ms:<8.0f} "
              f"{r.p99_latency_ms:<8.0f} {success_rate:<8.1f}% {r.rejected_requests:<6} {status}")

    print(f"\n{'='*70}")
    print(f"  测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="NF-SafetyHub 硬件能力评估工具")
    parser.add_argument("--base-url", required=True, help="SafetyHub 地址，如 http://192.168.1.100:8000/v1")
    parser.add_argument("--api-key", required=True, help="用于测试的 API Key")
    parser.add_argument("--model", default="deepseek-v4-flash", help="测试使用的模型名")
    parser.add_argument("--start", type=int, default=10, help="起始并发数 (默认 10)")
    parser.add_argument("--max", type=int, default=500, help="最大并发数 (默认 500)")
    parser.add_argument("--step", type=int, default=20, help="每级递增步长 (默认 20)")
    parser.add_argument("--duration", type=int, default=15, help="每级持续秒数 (默认 15)")
    parser.add_argument("--timeout", type=int, default=60, help="单次请求超时秒数 (默认 60)")

    args = parser.parse_args()

    tester = CapacityTester(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        timeout_seconds=args.timeout,
    )

    results = find_max_capacity(
        tester,
        start_concurrency=args.start,
        max_concurrency=args.max,
        step=args.step,
        duration_per_level=args.duration,
    )

    print_capacity_report(results)


if __name__ == "__main__":
    main()
