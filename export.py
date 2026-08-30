import json
import os
from main import get_team_report


print("📦 正在提取本周最新战报...")
# 确保文件夹存在
os.makedirs("docs/data", exist_ok=True)


# 抓取过去 7 天的数据
report_data = get_team_report(days=7)


# 写入静态 JSON 文件
with open("docs/data/latest.json", "w", encoding="utf-8") as f:
    json.dump(report_data, f, ensure_ascii=False, indent=2)


print("✅ docs/data/latest.json 生成成功！")
