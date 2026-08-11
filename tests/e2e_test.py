"""
============================================================
端到端测试：扫描 → 缺集计算 → MoviePilot 订阅 全流程
前置条件：
  1. mock_mp.py 已在 19000 端口运行
  2. 缺集管家已在 18999 端口运行
运行：python tests/e2e_test.py
============================================================
"""

import json
import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:18999"
SAMPLE = os.path.join(os.environ["TEMP"], "opencode", "sample_tv")

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {detail}")


def main():
    c = httpx.Client(base_url=BASE, timeout=30)

    print("== 0. 重置 Mock 数据（防止测试环境残留影响结果）==")
    r = httpx.delete("http://127.0.0.1:19000/reset", timeout=10)
    print(f"  重置结果: {r.json().get('message')}")

    print("== 0.5. 登录（首次设置密码 + 登录；已初始化时 setup 会失败，可忽略） ==")
    c.post("/api/auth/setup", json={"password": "e2e-test-pwd"})
    r = c.post("/api/auth/login", json={"password": "e2e-test-pwd"})
    check("登录成功", r.json()["success"], r.text)

    print("== 1. 配置设置（指向 mock MP + 示例 strm 目录）==")
    r = c.post("/api/settings", json={
        "mp_url": "http://127.0.0.1:19000",
        "mp_token": "test-token-123",
        "scan_paths": json.dumps([SAMPLE]),
        "auto_subscribe": "1",   # 顺便测试自动订阅
    })
    check("保存设置", r.json()["success"], r.text)

    r = c.post("/api/settings/test", json={
        "mp_url": "http://127.0.0.1:19000",
        "mp_token": "test-token-123",
        "scan_paths": json.dumps([SAMPLE]),
    })
    results = {x["name"]: x for x in r.json()["data"]}
    check("测试连接: MP", results["MoviePilot"]["ok"], results["MoviePilot"]["detail"])
    check("测试连接: TMDB代理", results["TMDB 数据"]["ok"], results["TMDB 数据"]["detail"])

    print("== 2. 开始扫描 ==")
    r = c.post("/api/scan")
    check("扫描启动", r.json()["success"], r.text)

    # 轮询扫描进度直到完成
    for _ in range(60):
        time.sleep(2)
        st = c.get("/api/scan/status").json()["data"]
        if not st["running"]:
            break
    check("扫描完成", not st["running"], st)
    if st.get("error"):
        check("扫描无错误", False, st["error"])

    print("== 3. 检查缺集结果 ==")
    r = c.get("/api/shows?filter=all").json()["data"]
    by_id = {s["tmdb_id"]: s for s in r["shows"]}

    # 权力的游戏 TMDB 1399：S01 已有 1,2,4，TMDB 共 6 集 → 缺 3,5,6
    show = by_id.get(1399)
    check("找到《权力的游戏》", show is not None)
    if show:
        s1 = next((s for s in show["seasons"] if s["season_number"] == 1), None)
        check("GoT S01 缺 3,5,6", s1 and s1["missing_episodes"] == [3, 5, 6], json.dumps(s1, ensure_ascii=False))
        check("GoT S01 状态 partial", s1 and s1["status"] == "partial")
        # 第 2 季完全没有文件 → 整季缺失
        s2 = next((s for s in show["seasons"] if s["season_number"] == 2), None)
        check("GoT S02 整季缺失", s2 and s2["status"] == "full_missing", json.dumps(s2, ensure_ascii=False))
        check("GoT 剧名清理正确", show["name"] == "权力的游戏", show["name"])

    # 老友记 TMDB 12345：S01 已有 1,2,3，TMDB 共 24 集 → 缺 4..24
    show = by_id.get(12345)
    check("找到《老友记》", show is not None)
    if show:
        s1 = next((s for s in show["seasons"] if s["season_number"] == 1), None)
        check("老友记 S01 缺 4-24",
              s1 and s1["missing_episodes"] == list(range(4, 25)),
              json.dumps(s1["missing_episodes"][:5], ensure_ascii=False) if s1 else "")

    # 毒枭 TMDB 63351：S01 有 1 集（共8）缺 2..8；S02 有 5（共10）缺 1-4,6-10
    show = by_id.get(63351)
    check("找到《毒枭》", show is not None)
    if show:
        s1 = next((s for s in show["seasons"] if s["season_number"] == 1), None)
        check("毒枭 S01 缺 2-8", s1 and s1["missing_episodes"] == list(range(2, 9)), str(s1))

    print("== 4. 检查自动订阅 ==")
    r = c.get("/api/subscriptions").json()["data"]
    check("订阅管理可读", r["source"] == "mp", r)
    # 自动订阅开着 → 应该创建了 3 条（GoT S1, GoT S2, 老友记 S1, 毒枭 S1, 毒枭 S2 = 5 季全缺）
    subs = r["subscriptions"]
    check("自动订阅数量 = 5", len(subs) == 5, f"实际 {len(subs)}: {[s['name'] for s in subs]}")

    # 订阅详情：缺少集应等于总集数
    if subs:
        first = subs[0]
        check("订阅含季信息", first["season"] is not None)

    print("== 5. 手动订阅去重（重复订阅同一季应被拒绝） ==")
    r = c.post("/api/shows/1399/subscribe", json={"season": 1})
    check("重复订阅被拦截", not r.json()["success"], r.text)

    print("== 6. 忽略功能 ==")
    r = c.post("/api/shows/63351/ignore", json={"season": 1})
    check("忽略毒枭 S01", r.json()["success"], r.text)
    r = c.get("/api/shows?filter=ignored").json()["data"]
    check("已忽略列表含毒枭",
          any(s["tmdb_id"] == 63351 and any(se["ignored"] for se in s["seasons"]) for s in r["shows"]))

    print("== 7. 删除订阅 ==")
    subs = c.get("/api/subscriptions").json()["data"]["subscriptions"]
    if subs:
        r = c.delete(f"/api/subscriptions/{subs[0]['mp_id']}")
        check("删除订阅", r.json()["success"], r.text)
        after = c.get("/api/subscriptions").json()["data"]
        check("订阅数量减一", after["total"] == len(subs) - 1, after)

    print("== 8. 概览统计 ==")
    ov = c.get("/api/overview").json()["data"]
    check("统计: 剧集数=3", ov["show_count"] == 3, ov)
    check("统计: 整季缺失数>0", ov["full_missing_seasons"] > 0, ov)

    print("== 9. 日志 ==")
    logs = c.get("/api/logs?limit=20").json()["data"]
    check("日志可读", len(logs) > 0)

    print(f"\n========== 结果：通过 {passed}，失败 {failed} ==========")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
