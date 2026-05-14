import random
import re

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, register


@register("xxt_fun", "mico-v", "学习通模仿娱乐插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    @filter.command("选人")
    async def pick_members(self, event: AstrMessageEvent):
        """随机@QQ群成员。用法：/选人 人数"""
        if not event.get_group_id():
            yield event.plain_result("该指令仅支持群聊使用。")
            return

        match = re.search(r"(\d+)", event.message_str or "")
        if not match:
            yield event.plain_result("用法：/选人 人数，例如 /选人 3")
            return

        pick_count = int(match.group(1))
        if pick_count <= 0:
            yield event.plain_result("人数必须大于 0。")
            return

        group = await event.get_group()
        if not group or not group.members:
            yield event.plain_result("读取群成员失败，请确认当前平台为 QQ(OneBot) 并重试。")
            return

        bot_self_id = event.get_self_id()
        members = [m for m in group.members if str(m.user_id) != str(bot_self_id)]
        if not members:
            yield event.plain_result("群成员列表为空，无法选人。")
            return
        if pick_count > len(members):
            yield event.plain_result(f"人数过多，当前可选成员共 {len(members)} 人。")
            return

        selected = random.sample(members, pick_count)
        chain = [Plain("随机选中：")]
        for idx, member in enumerate(selected):
            chain.append(At(qq=str(member.user_id)))
            if idx < pick_count - 1:
                chain.append(Plain(" "))
        yield event.chain_result(chain)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
