import os
import unittest
import json
import sqlite3
from fastapi.testclient import TestClient

# 强制设置测试用的环境变量
os.environ["OW_DB_PATH"] = "test_ow_data.db"
os.environ["OW_CONFIG_PATH"] = "test_config.json"

# 先创建测试配置，再导入 app 避免加载到错误的配置
TEST_CONFIG = {
    "TEAM_MEMBERS": [
        "源氏神#1234",
        "保活大王#5678",
        "盾牌猛击#9999",
        "爱心天使#8888"
    ],
    "HERO_MAPPING": {
        "reinhardt": "莱因哈特",
        "genji": "源氏",
        "ana": "安娜"
    }
}

with open("test_config.json", "w", encoding="utf-8") as f:
    json.dump(TEST_CONFIG, f, ensure_ascii=False, indent=2)

# 现在引入并初始化生成测试数据库
from generate_mock_data import generate_mock_db
generate_mock_db("test_ow_data.db")

from main import app

class TestOWTracker(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        pass

    @classmethod
    def tearDownClass(cls):
        # 跑完测试清理测试生成的临时文件
        for file in ["test_ow_data.db", "test_config.json"]:
            if os.path.exists(file):
                os.remove(file)

    def test_root_endpoint(self):
        """测试根路由是否正确返回 HTML 页面"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_report_api(self):
        """测试战报 API 核心计算逻辑和'大王'颁奖逻辑"""
        response = self.client.get("/api/report/7")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # 验证返回结构
        self.assertIn("period", data)
        self.assertIn("players", data)
        self.assertIn("awards", data)
        
        # 验证玩家数据是否完整，排除 or 包含 delta 的情况
        players = data["players"]
        self.assertEqual(len(players), 4) # 4个模拟玩家
        
        for p in players:
            self.assertTrue(p["has_delta"])
            self.assertIn("overall", p)
            self.assertIn("role_stats", p)
            self.assertIn("heroes", p)
        
        # 验证具体的“大王”颁发
        awards = data["awards"]
        # 保活大王死亡率极低且胜率高达80%，应该获得这两个奖
        self.assertEqual(awards.get("确实是会保活大王"), "保活大王#5678")
        self.assertEqual(awards.get("狗运小子（最佳胜率）"), "保活大王#5678")
        
        # 盾牌猛击 1 胜 7 负，1 个消灭 30 阵亡 30000 伤害，应该获得最爱回家大王、传奇刮痧大王与可能要等ELO
        self.assertEqual(awards.get("最爱回家大王"), "源氏神#1234") # 源氏神阵亡/10min 比例最高
        self.assertEqual(awards.get("传奇刮痧大王"), "盾牌猛击#9999")
        self.assertEqual(awards.get("可能真的要等ELO了"), "盾牌猛击#9999")
        
        # 源氏神伤害超高，且击杀最多
        self.assertEqual(awards.get("伤害确实是打满了大王"), "源氏神#1234")
        self.assertEqual(awards.get("真·杀意很大"), "源氏神#1234")
        
        # 爱心天使时长最长，治疗最高，助攻最高
        self.assertEqual(awards.get("应该就没在上班"), "爱心天使#8888")
        self.assertEqual(awards.get("本周小天使"), "爱心天使#8888")
        self.assertEqual(awards.get("真正的团队核心奉献之神"), "爱心天使#8888")

    def test_trend_api(self):
        """测试历史趋势趋势接口"""
        response = self.client.get("/api/trend/源氏神#1234?days=14")
        self.assertEqual(response.status_code, 200)
        trends = response.json()
        self.assertIsInstance(trends, list)
        self.assertGreater(len(trends), 0)
        
        # 检查趋势项内容
        trend_item = trends[0]
        self.assertIn("date", trend_item)
        self.assertIn("kda", trend_item)
        self.assertIn("deaths_10", trend_item)
        self.assertIn("dmg_10", trend_item)
        self.assertIn("heal_10", trend_item)

if __name__ == "__main__":
    unittest.main()
