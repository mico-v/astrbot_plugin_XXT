# astrbot_plugin_XXT

学习通模仿娱乐插件（QQ 群聊向）。

## 已实现功能

- `选人 <人数>`：读取当前 QQ 群成员并随机 @ 指定人数。
- `查撤回 [数量]`：管理员查询最近记录的撤回消息编号、发送时间和发送人，默认 5 条，最多 10 条。
- `重放 <编号>`：管理员按 `查撤回` 显示的编号重新发送撤回消息，支持重放合并转发聊天记录。
- `清空撤回`：管理员清空当前群的撤回消息记录。
- `课堂提醒 开/关/状态`：管理员控制课堂提醒功能开关，默认关闭。

## 课堂提醒说明

- 开启后：当群聊消息为上课时段内的发言，会提醒发言者“正在上课请先听课”。
- 当该用户被 `@` 且 60 秒内未回复时，会提醒该 `@` 人“对方在上课（具体课程）”。
- 需要在插件配置中设置 `class_periods`（上课时段），否则默认不触发课堂提醒。

示例配置（AstrBot 插件配置）：
```yaml
class_reminder_enabled: true
class_warning_cooldown_seconds: 60
class_reminder_reply_timeout_seconds: 60
class_periods:
  - start: "08:30"
    end: "10:00"
    name: "高数课"
  - start: "10:20"
    end: "12:00"
    name: "数据库"
```

## 防撤回说明

- 插件会暂存最近 2 分钟内收到的消息。
- 收到 OneBot 撤回通知后，匹配原消息并加入内存中的已撤回消息列表。
- 查询撤回记录不会直接展示消息内容；需要查看内容时，使用 `重放 <编号>`。
- 合并转发消息会优先在缓存时展开，重放时通过 OneBot 合并转发接口重新发送。
- 撤回记录最多保留 50 条，重启 AstrBot 后会清空。
- 该功能依赖 QQ/OneBot 适配器向 AstrBot 上报撤回通知。

> [!NOTE]
> This repo is just a template of [AstrBot](https://github.com/AstrBotDevs/AstrBot) Plugin.
> 
> [AstrBot](https://github.com/AstrBotDevs/AstrBot) is an agentic assistant for both personal and group conversations. It can be deployed across dozens of mainstream instant messaging platforms, including QQ, Telegram, Feishu, DingTalk, Slack, LINE, Discord, Matrix, etc. In addition, it provides a reliable and extensible conversational AI infrastructure for individuals, developers, and teams. Whether you need a personal AI companion, an intelligent customer support agent, an automation assistant, or an enterprise knowledge base, AstrBot enables you to quickly build AI applications directly within your existing messaging workflows.

# Supports

- [AstrBot Repo](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot Plugin Development Docs (Chinese)](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot Plugin Development Docs (English)](https://docs.astrbot.app/en/dev/star/plugin-new.html)
