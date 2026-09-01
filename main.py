import sqlite3
import json
import os
from datetime import datetime, timedelta, timezone as dt_timezone
from contextlib import asynccontextmanager
import subprocess


import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles  # 👈 新增引入


# 核心配置
APP_VERSION = "V2.8"  # 👈 统一版本号管理
DB_PATH = "ow_data.db"
CONFIG_PATH = "config.json"
LOCAL_TZ = "America/Los_Angeles" # 强行锁定加州时间


# --- 英雄职业字典（用于一拆三） ---
ROLE_MAP = {
    "tank": ["dva", "doomfist", "junker-queen", "mauga", "orisa", "ramattra", "reinhardt", "roadhog", "sigma", "winston", "wrecking-ball", "zarya"],
    "damage": ["ashe", "bastion", "cassidy", "echo", "genji", "hanzo", "junkrat", "mei", "pharah", "reaper", "sojourn", "soldier-76", "sombra", "symmetra", "torbjorn", "tracer", "venture", "widowmaker"],
    "support": ["ana", "baptiste", "brigitte", "illari", "kiriko", "lifeweaver", "lucio", "mercy", "moira", "zenyatta"]
}


def get_role(hero_en):
    for role, heroes in ROLE_MAP.items():
        if hero_en in heroes: return role
    return "damage" # 默认防错


# 动态读取配置文件
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"TEAM_MEMBERS": [], "WXPUSHER_APP_TOKEN": "", "WXPUSHER_UIDS": []}


scheduler = BackgroundScheduler(timezone=LOCAL_TZ)


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


# --- 核心抓取逻辑 (带智能去重) ---
def fetch_and_save_all_sync():
    config = load_config()
    team_members = config.get("TEAM_MEMBERS", [])
    
    print(f"[{datetime.now()}] 🚀 开始执行全队数据抓取任务...")
    if not team_members:
        print("⚠️ 未在 config.json 中找到队伍名单。")
        return


    with httpx.Client(timeout=30.0) as client:
        for tag in team_members:
            try:
                formatted_tag = tag.replace("#", "-")
                sum_res = client.get(f"https://overfast-api.tekrop.fr/players/{formatted_tag}/summary")
                stat_res = client.get(f"https://overfast-api.tekrop.fr/players/{formatted_tag}/stats/summary")


                if sum_res.status_code == 200 and stat_res.status_code == 200:
                    summary_data = sum_res.json()
                    stats_data = stat_res.json()
                    
                    new_time = stats_data.get("general", {}).get("time_played", 0)


                    with sqlite3.connect(DB_PATH) as conn:
                        row = conn.execute("SELECT raw_data FROM snapshots WHERE battle_tag=? ORDER BY timestamp DESC LIMIT 1", (tag,)).fetchone()
                        
                        if row:
                            last_data = json.loads(row[0])
                            last_time = last_data.get("stats", {}).get("general", {}).get("time_played", 0)
                            if new_time == last_time:
                                print(f"⏩ {tag} 数据无变动，跳过入库。")
                                continue


                        payload = {"summary": summary_data, "stats": stats_data}
                        conn.execute(
                            "INSERT INTO snapshots (battle_tag, timestamp, raw_data) VALUES (?, ?, ?)",
                            (tag, datetime.now(dt_timezone.utc).isoformat(), json.dumps(payload))
                        )
                        conn.commit()
                    print(f"✅ {tag} 发现新数据！快照已保存。")
                else:
                    print(f"⚠️ {tag} 抓取失败，状态码: Summary {sum_res.status_code}")
            except Exception as e:
                print(f"❌ {tag} 抓取异常: {e}")


# --- 微信推送逻辑 ---
def send_wechat_report_sync():
    print(f"[{datetime.now()}] 📱 准备发送微信车队战报...")
    config = load_config()
    app_token = config.get("WXPUSHER_APP_TOKEN", "")
    uids = config.get("WXPUSHER_UIDS", [])


    if not app_token or not uids:
        print("⚠️ 缺少 WxPusher Token 或 UID 配置，取消发送")
        return


    report_data = get_team_report(days=7)
    awards = report_data.get("awards", {})
    
    if not awards:
        print("无战报数据，取消发送")
        return


    content = f"""# 🏆 OW车队战力简报 ({APP_VERSION})
> 数据周期：过去 7 天


🥇 狗运小子（最佳胜率）：**{awards.get('狗运小子（最佳胜率）', '无')}**
🛡️ 确实是会保活大王：**{awards.get('确实是会保活大王', '无')}**
💀 最爱回家大王：**{awards.get('最爱回家大王', '无')}**
👼 本周小天使：**{awards.get('本周小天使', '无')}**
💥 伤害确实是打满了：**{awards.get('伤害确实是打满了大王', '无')}**
🤝 团队核心奉献之神：**{awards.get('真正的团队核心奉献之神', '无')}**
🔋 传奇刮痧大王：**{awards.get('传奇刮痧大王', '无')}**
🥷 人头狗：**{awards.get('人头狗', '无')}**
🩸 真·杀意很大：**{awards.get('真·杀意很大', '无')}**
📉 可能要等ELO了：**{awards.get('可能真的要等ELO了', '无')}**
🎮 应该就没在上班：**{awards.get('应该就没在上班', '无')}**


👉 详情请查看最新静态周报看板。
"""


    payload = {
        "appToken": app_token,
        "content": content,
        "contentType": 3,
        "uids": uids
    }
    
    try:
        with httpx.Client() as client:
            client.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=10.0)
            print("✅ 微信推送成功！")
    except Exception as e:
        print(f"❌ 微信推送失败: {e}")


# --- 新增：静态页面导出与 Git 自动推送引擎 ---
def export_and_push_static():
    print(f"[{datetime.now()}] 📦 开始打包生成静态周报...")
    report_data = get_team_report(days=7)
    
    os.makedirs("docs/data", exist_ok=True)
    with open("docs/data/latest.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False)
        
    print(f"[{datetime.now()}] 🚀 开始推送到 GitHub Pages...")
    
    config = load_config()
    gh_token = config.get("GITHUB_TOKEN")
    gh_repo = config.get("GITHUB_REPO")
    
    if not gh_token or not gh_repo:
        print("❌ 缺少 GITHUB_TOKEN 或 GITHUB_REPO 配置，取消自动推送。")
        return

    try:
        # 1. 解决 Docker 挂载目录的所有权安全拦截
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "/app"], check=True)
        
        # 2. 配置机器人的 Git 提交身份
        subprocess.run(["git", "config", "--global", "user.email", "bot@owtracker.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "OW Tracker Bot"], check=True)
        
        # 3. 绑定带 Token 的鉴权地址 (静默免密推送)
        remote_url = f"https://{gh_token}@github.com/{gh_repo}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
        
        # 4. 暂存 docs 文件夹
        subprocess.run(["git", "add", "docs/"], check=True)
        
        # 5. 检查变动，无变动直接跳过
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("⏩ 本周数据无变化，跳过 GitHub 推送。")
            return
            
        # 6. 提交并推送至主分支
        subprocess.run(["git", "commit", "-m", f"docs: auto generate daily report {datetime.now().strftime('%Y-%m-%d')} ({APP_VERSION})"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✅ 静态网页数据已成功更新至 GitHub！")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git 命令执行失败 (退出码 {e.returncode}): {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 确保文件夹存在，防止挂载报错
    os.makedirs("docs/data", exist_ok=True)
    
    scheduler.add_job(fetch_and_save_all_sync, 'cron', hour=4, minute=0)
    scheduler.add_job(send_wechat_report_sync, 'cron', day_of_week='sun', hour=20, minute=0)
    scheduler.add_job(export_and_push_static, 'cron', hour=4, minute=5)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=f"OW Tracker {APP_VERSION}", lifespan=lifespan)


# 👈 核心修正：挂载数据目录供前端拉取
app.mount("/data", StaticFiles(directory="docs/data"), name="data")

@app.get("/")
def root():
    return FileResponse("docs/index.html")


@app.post("/api/snapshot/team/all")
def manual_snapshot():
    fetch_and_save_all_sync()
    return {"status": "success", "message": "已尝试抓取，无变动数据将被自动过滤"}


@app.post("/api/test_wechat")
def test_wechat_push():
    send_wechat_report_sync()
    return {"status": "success", "message": "已触发微信推送"}


# --- Delta 分析引擎 ---
def calc_delta(b, a):
    time_b = b.get("time_played", 0); time_a = a.get("time_played", 0) if a else 0
    d_time = time_b - time_a
    if d_time <= 0: return None


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
    target_time = (datetime.now(dt_timezone.utc) - timedelta(days=days)).isoformat()
    team_data = []
    player_deltas = {}
    
    config = load_config()
    team_members = config.get("TEAM_MEMBERS", [])


    with sqlite3.connect(DB_PATH) as conn:
        for tag in team_members:
            row_b = conn.execute("SELECT id, raw_data, timestamp FROM snapshots WHERE battle_tag=? ORDER BY timestamp DESC LIMIT 1", (tag,)).fetchone()
            row_a = conn.execute("SELECT id, raw_data, timestamp FROM snapshots WHERE battle_tag=? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (tag, target_time)).fetchone()
            
            if not row_a:
                row_a = conn.execute("SELECT id, raw_data, timestamp FROM snapshots WHERE battle_tag=? ORDER BY timestamp ASC LIMIT 1", (tag,)).fetchone()


            if not row_b: continue
            
            data_b = json.loads(row_b[1])
            summary = data_b.get("summary", {})
            
            if not row_a or row_a[0] == row_b[0]:
                team_data.append({"battle_tag": tag, "summary": summary, "has_delta": False})
                continue
                
            data_a = json.loads(row_a[1])
            stats_b = data_b.get("stats", {})
            stats_a = data_a.get("stats", {})


            gen_b = stats_b.get("general", {}); gen_a = stats_a.get("general", {})
            overall_delta = calc_delta(gen_b, gen_a)


            if not overall_delta:
                team_data.append({"battle_tag": tag, "summary": summary, "has_delta": False})
                continue


            heroes_b = stats_b.get("heroes", {}); heroes_a = stats_a.get("heroes", {})
            hero_deltas = []


            role_stats = {
                "tank": {"time_played":0, "elims":0, "deaths":0, "damage":0, "healing":0, "assists":0},
                "damage": {"time_played":0, "elims":0, "deaths":0, "damage":0, "healing":0, "assists":0},
                "support": {"time_played":0, "elims":0, "deaths":0, "damage":0, "healing":0, "assists":0}
            }
            
            hero_mapping = config.get("HERO_MAPPING", {})
            
            for h_name, h_data_b in heroes_b.items():
                h_data_a = heroes_a.get(h_name)
                hd = calc_delta(h_data_b, h_data_a)
                if hd:
                    role = get_role(h_name)
                    
                    for k in role_stats[role].keys():
                        role_stats[role][k] += hd.get(k, 0)


                    cn_name = hero_mapping.get(h_name, h_name.capitalize())
                    hd["hero"] = cn_name
                    hd["hero_en"] = h_name 
                    hd["role"] = role      
                    hero_deltas.append(hd)
                    
            hero_deltas.sort(key=lambda x: x["time_played"], reverse=True)
            
            player_deltas[tag] = overall_delta
            
            vods = config.get("VODS", {}).get(tag, [])


            team_data.append({
                "battle_tag": tag,
                "summary": summary,
                "has_delta": True,
                "overall": overall_delta,
                "role_stats": role_stats,
                "heroes": hero_deltas,
                "vods": vods 
            })


    # 颁发大王
    awards = {}
    if player_deltas:
        def get_winner(metric_fn, reverse=False, min_time=600):
            candidates = {t: metric_fn(d) for t, d in player_deltas.items() if d["time_played"] >= min_time}
            if not candidates: return "无（未满足出场时长）"
            return sorted(candidates.items(), key=lambda x: x[1], reverse=reverse)[0][0]


        awards["狗运小子（最佳胜率）"] = get_winner(lambda d: d["wins"] / max(1, d["wins"]+d["losses"]), reverse=True)
        awards["确实是会保活大王"] = get_winner(lambda d: (d["deaths"] / d["time_played"]) * 600, reverse=False)
        awards["最爱回家大王"] = get_winner(lambda d: (d["deaths"] / d["time_played"]) * 600, reverse=True)
        awards["本周小天使"] = get_winner(lambda d: (d["healing"] / d["time_played"]) * 600, reverse=True)
        awards["伤害确实是打满了大王"] = get_winner(lambda d: (d["damage"] / d["time_played"]) * 600, reverse=True)
        awards["真正的团队核心奉献之神"] = get_winner(lambda d: ((d["elims"] + d["assists"]) / d["time_played"]) * 600, reverse=True)
        awards["传奇刮痧大王"] = get_winner(lambda d: d["damage"] / max(1, d["elims"]), reverse=True)
        awards["人头狗"] = get_winner(lambda d: d["damage"] / max(1, d["elims"]), reverse=False)
        awards["真·杀意很大"] = get_winner(lambda d: (d["elims"] / d["time_played"]) * 600, reverse=True)
        awards["可能真的要等ELO了"] = get_winner(lambda d: d["losses"], reverse=True)
        awards["应该就没在上班"] = get_winner(lambda d: d["time_played"], reverse=True, min_time=0)


    return {"period": days, "players": team_data, "awards": awards}


# --- 趋势 API ---
@app.get("/api/trend/{battle_tag}")
def get_player_trend(battle_tag: str, days: int = 14):
    target_time = (datetime.now(dt_timezone.utc) - timedelta(days=days)).isoformat()
    trends = []
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT timestamp, raw_data FROM snapshots WHERE battle_tag=? AND timestamp >= ? ORDER BY timestamp ASC", (battle_tag, target_time)).fetchall()
        
    for i in range(1, len(rows)):
        prev_time, prev_raw = rows[i-1]
        curr_time, curr_raw = rows[i]
        
        prev_data = json.loads(prev_raw).get("stats", {}).get("general", {})
        curr_data = json.loads(curr_raw).get("stats", {}).get("general", {})
        
        delta = calc_delta(curr_data, prev_data)
        if delta and delta["time_played"] > 60:
            date_str = curr_time[5:10] + " " + curr_time[11:16]
            
            elims = delta["elims"]
            assists = delta["assists"]
            deaths = max(1, delta["deaths"])
            time_played = delta["time_played"]
            
            kda = (elims + assists) / deaths
            deaths_10 = (delta["deaths"] / time_played) * 600
            dmg_10 = (delta["damage"] / time_played) * 600
            heal_10 = (delta["healing"] / time_played) * 600
            
            trends.append({
                "date": date_str,
                "kda": round(kda, 2),
                "deaths_10": round(deaths_10, 1),
                "dmg_10": round(dmg_10, 0),
                "heal_10": round(heal_10, 0)
            })
    return trends
