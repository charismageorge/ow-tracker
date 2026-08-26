import sqlite3
import json
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

DB_PATH = "ow_data.db"
# 替换为你们车队的真实 ID
TEAM_MEMBERS = ["George666-11942", "HarryOtter-11657", "Probability-11240", "DoubleX-11153"]

scheduler = BackgroundScheduler()

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                battle_tag TEXT,
                timestamp DATETIME,
                raw_data TEXT
            )
        ''')
        conn.commit()

# --- 核心抓取逻辑 ---
async def fetch_and_save_all():
    print(f"[{datetime.now()}] 🚀 开始执行全队数据抓取任务...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        for tag in TEAM_MEMBERS:
            try:
                formatted_tag = tag.replace("#", "-")
                sum_res = await client.get(f"https://overfast-api.tekrop.fr/players/{formatted_tag}/summary")
                stat_res = await client.get(f"https://overfast-api.tekrop.fr/players/{formatted_tag}/stats/summary")

                if sum_res.status_code == 200 and stat_res.status_code == 200:
                    payload = {"summary": sum_res.json(), "stats": stat_res.json()}
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute(
                            "INSERT INTO snapshots (battle_tag, timestamp, raw_data) VALUES (?, ?, ?)",
                            (tag, datetime.now(timezone.utc).isoformat(), json.dumps(payload))
                        )
                        conn.commit()
                    print(f"✅ {tag} 快照已保存")
                else:
                    print(f"⚠️ {tag} 抓取失败，状态码: Summary {sum_res.status_code}, Stats {stat_res.status_code}")
            except Exception as e:
                print(f"❌ {tag} 抓取异常: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 每天凌晨 4:00 执行定时快照，沉淀历史数据
    scheduler.add_job(fetch_and_save_all, 'cron', hour=4, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="OW Tracker V2.0", lifespan=lifespan)

@app.get("/")
def root():
    return FileResponse("index.html")

@app.post("/api/snapshot/team/all")
async def manual_snapshot():
    """手动触发全队抓取（用于测试或强制刷新）"""
    await fetch_and_save_all()
    return {"status": "success", "message": "全队数据已更新"}

# --- V2.0 核心：Delta 分析引擎 ---
def calc_delta(b, a):
    """计算两个数据块的差值 (B - A)"""
    time_b = b.get("time_played", 0)
    time_a = a.get("time_played", 0) if a else 0
    d_time = time_b - time_a
    if d_time <= 0: return None # 没玩过直接过滤

    wins_b = b.get("games_won", 0); wins_a = a.get("games_won", 0) if a else 0
    loss_b = b.get("games_lost", 0); loss_a = a.get("games_lost", 0) if a else 0
    
    tot_b = b.get("total", {}); tot_a = a.get("total", {}) if a else {}
    def d(key): return max(0, tot_b.get(key, 0) - tot_a.get(key, 0))

    return {
        "time_played": d_time,
        "wins": max(0, wins_b - wins_a),
        "losses": max(0, loss_b - loss_a),
        "elims": d("eliminations"),
        "assists": d("assists"),
        "deaths": d("deaths"),
        "damage": d("damage"),
        "healing": d("healing")
    }

@app.get("/api/report/{days}")
def get_team_report(days: int = 7):
    """获取过去 N 天的纯净差值战报"""
    target_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    team_data = []
    player_deltas = {} # 用于评奖

    with sqlite3.connect(DB_PATH) as conn:
        for tag in TEAM_MEMBERS:
            # 1. 找最新快照 B
            row_b = conn.execute("SELECT id, raw_data, timestamp FROM snapshots WHERE battle_tag=? ORDER BY timestamp DESC LIMIT 1", (tag,)).fetchone()
            # 2. 找 N 天前那段时间的最早快照 A
            row_a = conn.execute("SELECT id, raw_data, timestamp FROM snapshots WHERE battle_tag=? AND timestamp >= ? ORDER BY timestamp ASC LIMIT 1", (tag, target_time)).fetchone()

            if not row_b: continue
            
            data_b = json.loads(row_b[1])
            summary = data_b.get("summary", {})
            
            # 如果只有一个快照，说明才刚建库，无法计算差值
            if not row_a or row_a[0] == row_b[0]:
                team_data.append({"battle_tag": tag, "summary": summary, "has_delta": False})
                continue
                
            data_a = json.loads(row_a[1])
            stats_b = data_b.get("stats", {})
            stats_a = data_a.get("stats", {})

            # 计算整体大盘差值
            gen_b = stats_b.get("general", {})
            gen_a = stats_a.get("general", {})
            overall_delta = calc_delta(gen_b, gen_a)

            if not overall_delta:
                team_data.append({"battle_tag": tag, "summary": summary, "has_delta": False})
                continue

            # 计算英雄层面的差值，自动过滤掉时间没变化的废弃英雄
            heroes_b = stats_b.get("heroes", {})
            heroes_a = stats_a.get("heroes", {})
            hero_deltas = []
            
            for h_name, h_data_b in heroes_b.items():
                h_data_a = heroes_a.get(h_name)
                hd = calc_delta(h_data_b, h_data_a)
                if hd:
                    hd["hero"] = h_name
                    hero_deltas.append(hd)
                    
            hero_deltas.sort(key=lambda x: x["time_played"], reverse=True)
            
            player_deltas[tag] = overall_delta
            team_data.append({
                "battle_tag": tag,
                "summary": summary,
                "has_delta": True,
                "overall": overall_delta,
                "heroes": hero_deltas
            })

    # --- 颁发“大王”称号 ---
    awards = {}
    if player_deltas:
        def get_winner(metric_fn, reverse=False, min_time=600):
            # min_time=600 意味着这期间至少要玩 10 分钟才有资格拿奖
            candidates = {t: metric_fn(d) for t, d in player_deltas.items() if d["time_played"] >= min_time}
            if not candidates: return "虚位以待"
            return sorted(candidates.items(), key=lambda x: x[1], reverse=reverse)[0][0]

        awards["狗运小子（最佳胜率）"] = get_winner(lambda d: d["wins"] / max(1, d["wins"]+d["losses"]), reverse=True)
        awards["确实是会保活大王"] = get_winner(lambda d: (d["deaths"] / d["time_played"]) * 600, reverse=False)
        awards["最爱回家大王"] = get_winner(lambda d: (d["deaths"] / d["time_played"]) * 600, reverse=True)
        awards["本周小天使"] = get_winner(lambda d: (d["healing"] / d["time_played"]) * 600, reverse=True)
        awards["伤害确实是打满了大王"] = get_winner(lambda d: (d["damage"] / d["time_played"]) * 600, reverse=True)
        awards["真正的团队核心奉献之神"] = get_winner(lambda d: (d["assists"] / d["time_played"]) * 600, reverse=True)
        awards["传奇刮痧大王"] = get_winner(lambda d: d["damage"] / max(1, d["elims"]), reverse=True)
        awards["人头狗"] = get_winner(lambda d: d["damage"] / max(1, d["elims"]), reverse=False)
        awards["真·杀意很大"] = get_winner(lambda d: (d["elims"] / d["time_played"]) * 600, reverse=True)
        awards["可能真的要等ELO了"] = get_winner(lambda d: d["losses"], reverse=True)
        awards["应该就没在上班"] = get_winner(lambda d: d["time_played"], reverse=True, min_time=0)

    return {"period": days, "players": team_data, "awards": awards}

