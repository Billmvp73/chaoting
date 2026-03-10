#!/usr/bin/env python3
"""
apply-agent-skills.py — 将 config/agent-skills.json 中的 skill 配置
应用到 ~/.themachine/themachine.json 中对应的 agent 条目。

用法：
  python3 apply-agent-skills.py [--dry-run]

参数：
  --dry-run   打印将要应用的变更，但不实际写入文件

说明：
  - 读取本仓库 config/agent-skills.json
  - 读取 ~/.themachine/themachine.json
  - 对每个 agents.list 中的朝廷部门 agent，设置 skills 字段
  - 生成备份 ~/.themachine/themachine.json.bak-skill-config
  - 写入修改后的配置
  - 需要重启 TheMachine 生效（或通过 gateway restart）
"""

import json
import os
import sys
import shutil
from datetime import datetime

THEMACHINE_JSON = os.path.expanduser("~/.themachine/themachine.json")
SKILLS_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "agent-skills.json")
DRY_RUN = "--dry-run" in sys.argv

# 朝廷部门 agent IDs
CHAOTING_AGENTS = {
    "silijian", "zhongshu",
    "jishi_tech", "jishi_risk", "jishi_compliance", "jishi_resource",
    "bingbu", "gongbu", "libu", "libu_hr", "xingbu", "hubu"
}


def main():
    # Load skill config
    with open(SKILLS_CONFIG, "r") as f:
        skill_cfg = json.load(f)

    agent_skills = skill_cfg["agents"]

    # Load themachine.json
    with open(THEMACHINE_JSON, "r") as f:
        tm = json.load(f)

    agents_list = tm["agents"]["list"]

    changes = []
    for agent in agents_list:
        agent_id = agent.get("id")
        if agent_id not in CHAOTING_AGENTS:
            continue

        new_skills = agent_skills.get(agent_id, {}).get("skills")
        if new_skills is None:
            continue

        old_skills = agent.get("skills")
        if old_skills == new_skills:
            print(f"  [SKIP] {agent_id}: skills unchanged")
            continue

        changes.append({
            "id": agent_id,
            "old": old_skills,
            "new": new_skills,
            "comment": agent_skills[agent_id].get("comment", ""),
        })

        if not DRY_RUN:
            agent["skills"] = new_skills

    # Print summary
    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Agent Skill Changes:")
    print("-" * 60)
    for c in changes:
        old_str = str(c["old"]) if c["old"] is not None else "(all skills / unset)"
        print(f"\n  {c['id']} — {c['comment']}")
        print(f"    Before: {old_str}")
        print(f"    After:  {c['new']}")

    if not changes:
        print("  No changes needed.")
        return

    print(f"\nTotal agents modified: {len(changes)}")

    if DRY_RUN:
        print("\n[DRY RUN] No files written. Remove --dry-run to apply.")
        return

    # Backup
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = THEMACHINE_JSON + f".bak-skill-config-{ts}"
    shutil.copy2(THEMACHINE_JSON, backup_path)
    print(f"\nBackup created: {backup_path}")

    # Write
    with open(THEMACHINE_JSON, "w") as f:
        json.dump(tm, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Written: {THEMACHINE_JSON}")
    print("\n⚠️  需要重启 TheMachine 使配置生效：")
    print("   gateway restart")
    print("   或通过 chaoting CLI: themachine gateway restart")


if __name__ == "__main__":
    main()
