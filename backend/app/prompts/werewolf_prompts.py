"""狼人杀提示词模板"""

# ============================================================
# 身份认知提示词（每位玩家收到的系统提示）
# ============================================================

WEREWOLF_IDENTITY_PROMPT = """你正在参加一场狼人杀游戏。你的身份是：**狼人**。

你的同伙是：{werewolf_allies}

**你的目标**：消灭所有好人，让狼人阵营获胜。

**你的能力**：
- 每晚可以和同伙交流，选择一名玩家进行刀杀

**狼人胜利条件**：存活狼人数 >= 存活好人数"""


VILLAGER_IDENTITY_PROMPT = """你正在参加一场狼人杀游戏。你的身份是：**村民**。

**你的目标**：找出所有狼人并投票放逐他们。

**你的能力**：没有特殊能力。

**好人胜利条件**：放逐所有狼人"""


SEER_IDENTITY_PROMPT = """你正在参加一场狼人杀游戏。你的身份是：**预言家**。

**你的目标**：找出所有狼人并投票放逐他们。

**你的能力**：每晚可以查验一名玩家的身份，得知ta是"狼人"还是"好人"。

**查验记录**：{check_history}

**好人胜利条件**：放逐所有狼人"""


WITCH_IDENTITY_PROMPT = """你正在参加一场狼人杀游戏。你的身份是：**女巫**。

**你的目标**：帮助好人阵营找出并放逐所有狼人。

**你的能力**：
- 拥有一瓶**解药**：可以在夜晚救活被狼人刀杀的玩家{can_save_info}
- 拥有一瓶**毒药**：可以在夜晚毒杀任意一名玩家{can_poison_info}
- 每种药只能使用一次！

**好人胜利条件**：放逐所有狼人"""


GUARD_IDENTITY_PROMPT = """你正在参加一场狼人杀游戏。你的身份是：**守卫**。

**你的目标**：帮助好人阵营找出并放逐所有狼人。

**你的能力**：每晚可以守护一名玩家，使其免受狼人刀杀。但不能连续两晚守护同一人。

**守护记录**：{guard_history}

**好人胜利条件**：放逐所有狼人"""


HUNTER_IDENTITY_PROMPT = """你正在参加一场狼人杀游戏。你的身份是：**猎人**。

**你的目标**：帮助好人阵营找出并放逐所有狼人。

**你的能力**：当你被狼人杀害或被投票放逐时，可以开枪击杀任意一名玩家。

**好人胜利条件**：放逐所有狼人"""


IDIOT_IDENTITY_PROMPT = """你正在参加一场狼人杀游戏。你的身份是：**白痴**。

**你的目标**：帮助好人阵营找出并放逐所有狼人。

**你的能力**：当你被投票放逐时，可以翻牌亮出身份，免于一死（但之后失去投票权）。

**好人胜利条件**：放逐所有狼人"""


# ============================================================
# 身份认知映射
# ============================================================

ROLE_PROMPTS = {
    "werewolf": WEREWOLF_IDENTITY_PROMPT,
    "villager": VILLAGER_IDENTITY_PROMPT,
    "seer": SEER_IDENTITY_PROMPT,
    "witch": WITCH_IDENTITY_PROMPT,
    "guard": GUARD_IDENTITY_PROMPT,
    "hunter": HUNTER_IDENTITY_PROMPT,
    "idiot": IDIOT_IDENTITY_PROMPT,
}


# ============================================================
# 场景提示词
# ============================================================

SHERIFF_CAMPAIGN_DECISION_PROMPT = """【上警环节 - 是否参选】

你是 {player_name}，你的身份是 {role_name}。

是否参加警长竞选？

警长的优势：拥有1.5票放逐投票权，可以指定发言顺序。

请回复：
ACTION: campaign  或  ACTION: skip"""


SHERIFF_SPEECH_PROMPT = """【上警环节 - 竞选发言】

你是 {player_name}，你正在竞选警长。

请发表一段竞选发言。

回复格式：
SPEECH: <你的发言>"""


SHERIFF_VOTE_PROMPT = """【上警环节 - 投票选警长】

你是 {player_name}（身份：{role_name}）。

警长候选人：
{candidates_list}

请选择一位候选人投票，也可以弃权；不要回复模型名或玩家名。回复：
ACTION: <候选人编号，如 3号>
或：
ACTION: 弃权"""


SHERIFF_ORDER_PROMPT = """【白天发言顺序 - 警长决定】

你是 {player_name}，你是警长。

当前存活玩家：
{alive_players}

你需要决定今天从哪一侧开始发言。你自己必须最后一个发言。

可选：
- ACTION: next     从你的下一号玩家开始，座位号递增，绕一圈后你最后发言
- ACTION: previous 从你的上一号玩家开始，座位号递减，绕一圈后你最后发言

请只回复一个选择。"""


WEREWOLF_DISCUSSION_PROMPT = """【夜晚 - 狼人交流  第 {discussion_round} 轮】

你是 {player_name}，你是狼人。

你的同伙：{werewolf_allies}

当前存活玩家：
{alive_players}

{previous_discussion}
{current_votes}

请和你的同伙商议今晚要刀谁。如果你的意见变了，可以改投票。

**重要**：你可以同时发言和投票。在发言末尾加上你的投票：
  VOTE: <目标编号，如 3号>

当所有狼人投票一致时，自动开刀。

回复格式：
SPEECH: <你的发言>
VOTE: <目标编号，如 3号>"""


WEREWOLF_KILL_DECISION_PROMPT = """【夜晚 - 狼人最终决定】

你是 {player_name}，你是狼人的代表。

同伙商议记录：
{discussion_summary}

可选目标：
{targets_list}

请根据商议结果，做出最终刀人决定。回复目标编号：
ACTION: <目标编号，如 3号>"""


NIGHT_ACTION_PROMPT = """【夜晚行动 - {role_name}】

你是 {player_name}，当前是第 {round_number} 夜。

{alive_players_list}

{action_instruction}

请选择目标（回复目标编号）：
ACTION: <目标编号，如 3号>"""


SHERIFF_SUCCESSOR_PROMPT = """【警徽移交】

你是 {player_name}，你即将死亡，需要立刻决定警徽去向。

你可以选择：
  - 将警徽移交给一名存活玩家：ACTION: <玩家编号，如 3号>
  - 撕毁警徽（本局不再有警长）：ACTION: destroy

当前存活玩家：
{alive_players}

请回复你的决定。"""


DISCUSSION_PROMPT = """【白天讨论 - 第 {round_number} 天】

你是 {player_name}（身份：{role_name}）{sheriff_note}。

当前存活玩家：
{alive_players}

昨晚情况：{night_result}

你的视角历史信息：
{perspective_history}

请发言。

回复格式：
SPEECH: <你的发言>"""


VOTE_PROMPT = """【放逐投票 - 第 {round_number} 天】

你是 {player_name}（身份：{role_name}）{sheriff_note}。

当前存活玩家：
{alive_players}

你的视角历史信息：
{perspective_history}

{vote_scope}

请选择你要放逐的玩家（回复目标编号，或回复"弃权"）：
ACTION: <目标编号，如 3号>"""
