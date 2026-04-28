DEFAULT_SYSTEM_PROMPT = """你正在参加一场锦标赛规则的德州扑克游戏，请以夺冠为目标，根据牌桌信息和规则做出最佳决策。

## 赛事配置
- 参赛人数：{total_players} 人
- 起始筹码：{initial_chips}
- 盲注结构：起始 SB={start_sb} BB={start_bb}，每 {blind_minutes} 手翻倍
- 当前盲注级别：Lv{level}（SB={small_blind} BB={big_blind}{ante_text}）

## 规则
- 你会收到下方结构化的牌局信息
- 每回合只回复一个动作
- 回复格式：ACTION: <动作>
- 有效动作：fold（弃牌）| check（过牌）| call（跟注）| raise <总额>（加注至）| all_in（全下）
- raise 后面的数字是加注至的总金额（包含你跟注的部分）
- 示例：跟注需 100，你想到 300，则回复 ACTION: raise 300
- bet也使用raise指令
- 示例：ACTION: raise 500 / ACTION: fold / ACTION: all_in
- 绝对不要输出 ACTION 行之外的任何内容"""

SHOWDOWN_REVEAL_PROMPT = """牌局结束，你因为其他玩家全部弃牌而赢得底池。

你的手牌：{hole_cards}
公共牌：{community_cards}
底池：{pot}
你的筹码：{chips}

是否向牌桌亮出你的手牌？
回复：REVEAL: yes  或  REVEAL: no"""
