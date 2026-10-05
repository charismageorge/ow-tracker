import json
import sqlite3
from datetime import datetime, timezone, timedelta

def mock_player_data(battle_tag, name, avatar, base_time, base_wins, base_losses, base_elims, base_assists, base_deaths, base_damage, base_healing, delta_active=True):
    """
    生成一个符合 Overfast API 格式的玩家 summary 和 stats。
    """
    summary = {
        "username": name,
        "avatar": avatar,
        "title": "测试玩家",
        "endorsement": {"level": 3, "frame": "https://example.com/frame.png"},
        "competitive": {"pc": {"tank": {"division": "gold", "tier": 3}}}
    }
    
    # 构造英雄数据，简单拆分成 T, D, S 常用英雄
    heroes = {
        "reinhardt": { # Tank
            "time_played": base_time * 0.3,
            "games_won": int(base_wins * 0.3),
            "games_lost": int(base_losses * 0.3),
            "total": {
                "eliminations": int(base_elims * 0.3),
                "assists": int(base_assists * 0.3),
                "deaths": int(base_deaths * 0.3),
                "damage": int(base_damage * 0.3),
                "healing": 0
            }
        },
        "genji": { # Damage
            "time_played": base_time * 0.4,
            "games_won": int(base_wins * 0.4),
            "games_lost": int(base_losses * 0.4),
            "total": {
                "eliminations": int(base_elims * 0.5),
                "assists": int(base_assists * 0.2),
                "deaths": int(base_deaths * 0.5),
                "damage": int(base_damage * 0.5),
                "healing": 0
            }
        },
        "ana": { # Support
            "time_played": base_time * 0.3,
            "games_won": int(base_wins * 0.3),
            "games_lost": int(base_losses * 0.3),
            "total": {
                "eliminations": int(base_elims * 0.2),
                "assists": int(base_assists * 0.5),
                "deaths": int(base_deaths * 0.2),
                "damage": int(base_damage * 0.2),
                "healing": base_healing
            }
        }
    }
    
    stats = {
        "general": {
            "time_played": base_time,
            "games_won": base_wins,
            "games_lost": base_losses,
            "total": {
                "eliminations": base_elims,
                "assists": base_assists,
                "deaths": base_deaths,
                "damage": base_damage,
                "healing": base_healing
            }
        },
        "heroes": heroes
    }
    
    return {"summary": summary, "stats": stats}

def generate_mock_db(db_path="ow_data.db"):
    print(f"🛠️ 正在生成测试数据库: {db_path} ...")
    
    # 模拟数据成员
    members = [
        {"tag": "源氏神#1234", "name": "源氏神", "avatar": "https://d15f34w2p8l1cc.cloudfront.net/overwatch/7e74cb2e44cfdc1604a3eb3b4f62083bc701f8d4.png"},
        {"tag": "保活大王#5678", "name": "保活大王", "avatar": "https://d15f34w2p8l1cc.cloudfront.net/overwatch/9b3fdcfb17d1cf752c0dfb6c6b840f9de3cba2f3.png"},
        {"tag": "盾牌猛击#9999", "name": "盾牌猛击", "avatar": "https://d15f34w2p8l1cc.cloudfront.net/overwatch/20f4c390cb3eb2389d6fbbbe5fca315c2ba54271.png"},
        {"tag": "爱心天使#8888", "name": "爱心天使", "avatar": "https://d15f34w2p8l1cc.cloudfront.net/overwatch/2a8a7df0cb2e2a0f8bfdfcbce2a2c1409ab44171.png"}
    ]
    
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS snapshots")
    conn.execute('''
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battle_tag TEXT,
            timestamp DATETIME,
            raw_data TEXT
        )
    ''')
    
    now = datetime.now(timezone.utc)
    one_week_ago = now - timedelta(days=7, hours=1)
    two_weeks_ago = now - timedelta(days=14, hours=2)
    
    # 为每个玩家写入多条历史快照，用于测试趋势 API
    for idx, m in enumerate(members):
        for offset_days in [14, 10, 7, 4, 1, 0]:
            ts = now - timedelta(days=offset_days)
            # 让时间线性增长
            scale = (14 - offset_days)
            conn.execute("INSERT INTO snapshots (battle_tag, timestamp, raw_data) VALUES (?, ?, ?)",
                         (m["tag"], ts.isoformat(), json.dumps(
                             mock_player_data(m["tag"], m["name"], m["avatar"], 
                                              base_time=10000 + scale*1000, 
                                              base_wins=20 + scale*2, 
                                              base_losses=20 + scale*2, 
                                              base_elims=200 + scale*30, 
                                              base_assists=50 + scale*10, 
                                              base_deaths=100 + scale*15, 
                                              base_damage=150000 + scale*20000, 
                                              base_healing=10000 + scale*5000)
                         )))

    conn.commit()
    conn.close()
    print("✅ 测试数据 mock_db 生成完毕！")

if __name__ == "__main__":
    generate_mock_db()
