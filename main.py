import copy
import time
from collections import OrderedDict
import random
import re

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, register


MESSAGE_CACHE_TTL_SECONDS = 120
MAX_MESSAGE_CACHE_SIZE = 500
MAX_RECALLED_RECORDS = 50
MAX_QUERY_COUNT = 10


@register("xxt_fun", "mico-v", "学习通模仿娱乐插件", "1.2.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._recent_messages = OrderedDict()
        self._recalled_messages = []
        self._next_recalled_record_id = 1

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    @filter.event_message_type(filter.EventMessageType.ALL, priority=100)
    async def anti_recall_watcher(self, event: AstrMessageEvent):
        """暂存两分钟内消息，并在收到撤回通知时记录原消息。"""
        self._purge_expired_message_cache()

        raw = self._get_raw_message(event)
        if self._is_recall_event(raw):
            self._handle_recall_event(event, raw)
            return

        if self._is_cacheable_message(event, raw):
            await self._cache_message(event, raw)

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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("查撤回", alias={"查询撤回", "查询撤回消息", "撤回消息"})
    async def query_recalled_messages(self, event: AstrMessageEvent, count: int = 5):
        """管理员查询已记录的撤回消息。用法：/查撤回 [数量]"""
        if not event.get_group_id():
            yield event.plain_result("该指令仅支持群聊使用。")
            return

        if count <= 0:
            yield event.plain_result("查询数量必须大于 0。")
            return

        records = self._filter_recalled_records(event)[-min(count, MAX_QUERY_COUNT):]
        if not records:
            yield event.plain_result(
                "暂无已记录的撤回消息。仅能记录插件收到后两分钟内被撤回的消息。"
            )
            return

        yield event.chain_result(self._build_recalled_message_chain(records))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重放", alias={"重放撤回", "重新发送撤回"})
    async def replay_recalled_message(self, event: AstrMessageEvent):
        """管理员按编号重放已记录的撤回消息。用法：/重放 序号"""
        if not event.get_group_id():
            yield event.plain_result("该指令仅支持群聊使用。")
            return

        record_id = self._parse_positive_int(event.message_str or "")
        if not record_id:
            yield event.plain_result("用法：/重放 序号，例如 /重放 3。")
            return

        record = self._find_recalled_record(event, record_id)
        if record is None:
            yield event.plain_result(f"未找到编号 #{record_id} 的撤回消息。")
            return

        has_forward = self._record_has_forward(record)
        try:
            if await self._try_replay_with_onebot(event, record):
                return
        except Exception as exc:
            if has_forward:
                yield event.plain_result(f"重放失败：{exc}")
                return

        if has_forward:
            yield event.plain_result("重放合并转发需要 OneBot API，当前适配器无法发送。")
            return

        components = self._replay_message_components(record)
        if not components:
            yield event.plain_result("该撤回消息没有可重放的内容。")
            return
        yield event.chain_result(components)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("清空撤回", alias={"清空撤回消息"})
    async def clear_recalled_messages(self, event: AstrMessageEvent):
        """管理员清空当前群的撤回消息记录。"""
        group_id = self._normalize_id(event.get_group_id())
        if not group_id:
            yield event.plain_result("该指令仅支持群聊使用。")
            return

        before_count = len(self._recalled_messages)

        self._recalled_messages = [
            record
            for record in self._recalled_messages
            if record.get("group_id") != group_id
        ]
        cleared_count = before_count - len(self._recalled_messages)
        yield event.plain_result(f"已清空 {cleared_count} 条撤回消息记录。")

    def _get_raw_message(self, event):
        message_obj = getattr(event, "message_obj", None)
        for source in (message_obj, event):
            for attr_name in ("raw_message", "raw_event", "raw"):
                raw = getattr(source, attr_name, None)
                if raw is not None:
                    return raw
        return None

    def _raw_get(self, raw, key, default=None):
        if raw is None:
            return default
        if hasattr(raw, "get"):
            try:
                return raw.get(key, default)
            except TypeError:
                pass
        return getattr(raw, key, default)

    def _normalize_id(self, value):
        if value is None:
            return ""
        value = str(value).strip()
        return value

    def _is_recall_event(self, raw):
        post_type = self._raw_get(raw, "post_type")
        notice_type = self._raw_get(raw, "notice_type")
        if post_type and post_type != "notice":
            return False
        return notice_type in {
            "group_recall",
            "friend_recall",
            "message_recall",
            "recall",
        }

    def _is_cacheable_message(self, event, raw):
        message_obj = getattr(event, "message_obj", None)
        if not message_obj:
            return False

        post_type = self._raw_get(raw, "post_type")
        if post_type and post_type != "message":
            return False

        message_id = self._get_message_id(message_obj, raw)
        if not message_id:
            return False

        message_chain = getattr(message_obj, "message", None) or []
        message_str = getattr(message_obj, "message_str", "") or ""
        return bool(message_chain or message_str)

    def _get_message_id(self, message_obj, raw):
        raw_message_id = self._raw_get(raw, "message_id")
        if raw_message_id is not None:
            return self._normalize_id(raw_message_id)
        return self._normalize_id(getattr(message_obj, "message_id", ""))

    def _get_session_id(self, event, raw):
        group_id = self._normalize_id(self._raw_get(raw, "group_id"))
        if group_id:
            return group_id

        message_obj = getattr(event, "message_obj", None)
        if message_obj:
            group_id = self._normalize_id(getattr(message_obj, "group_id", ""))
            if group_id:
                return group_id
            session_id = self._normalize_id(getattr(message_obj, "session_id", ""))
            if session_id:
                return session_id

        get_group_id = getattr(event, "get_group_id", None)
        if callable(get_group_id):
            group_id = self._normalize_id(get_group_id())
            if group_id:
                return group_id

        return self._normalize_id(self._raw_get(raw, "user_id"))

    def _cache_key(self, session_id, message_id):
        return "{}:{}".format(session_id, message_id)

    async def _cache_message(self, event, raw):
        message_obj = event.message_obj
        message_id = self._get_message_id(message_obj, raw)
        session_id = self._get_session_id(event, raw)
        if not session_id or not message_id:
            return

        sender = getattr(message_obj, "sender", None)
        sender_id = self._normalize_id(
            getattr(sender, "user_id", "") or self._raw_get(raw, "user_id")
        )
        sender_name = self._normalize_id(getattr(sender, "nickname", "")) or sender_id
        group_id = self._normalize_id(
            getattr(message_obj, "group_id", "") or self._raw_get(raw, "group_id")
        )
        timestamp = self._int_or_default(
            self._raw_get(raw, "time")
            or getattr(message_obj, "timestamp", None)
            or int(time.time()),
            int(time.time()),
        )
        onebot_message = self._get_onebot_message(raw)
        forward_ids = self._extract_forward_ids(onebot_message)
        forward_nodes = []
        if forward_ids:
            try:
                forward_nodes = await self._load_forward_nodes(event, onebot_message)
            except Exception:
                forward_nodes = []

        record = {
            "message_id": message_id,
            "session_id": session_id,
            "group_id": group_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "time": timestamp,
            "cached_at": time.time(),
            "message_str": getattr(message_obj, "message_str", "") or "",
            "message": list(getattr(message_obj, "message", []) or []),
            "onebot_message": onebot_message,
            "forward_ids": forward_ids,
            "forward_nodes": forward_nodes,
        }

        self._recent_messages[self._cache_key(session_id, message_id)] = record
        while len(self._recent_messages) > MAX_MESSAGE_CACHE_SIZE:
            self._recent_messages.popitem(last=False)

    def _handle_recall_event(self, event, raw):
        message_id = self._normalize_id(self._raw_get(raw, "message_id"))
        if not message_id:
            return

        session_id = self._get_session_id(event, raw)
        record = self._recent_messages.pop(
            self._cache_key(session_id, message_id), None
        )

        if record is None:
            record = self._pop_cached_message_by_id(session_id, message_id)
        if record is None:
            return

        record = dict(record)
        record["record_id"] = self._next_recalled_record_id
        self._next_recalled_record_id += 1
        record["recall_time"] = int(time.time())
        record["operator_id"] = self._normalize_id(self._raw_get(raw, "operator_id"))
        self._recalled_messages.append(record)

        if len(self._recalled_messages) > MAX_RECALLED_RECORDS:
            self._recalled_messages = self._recalled_messages[-MAX_RECALLED_RECORDS:]

    def _pop_cached_message_by_id(self, session_id, message_id):
        for key, record in list(self._recent_messages.items()):
            if record.get("message_id") != message_id:
                continue
            if session_id and record.get("session_id") != session_id:
                continue
            return self._recent_messages.pop(key)
        return None

    def _purge_expired_message_cache(self):
        now = time.time()
        for key, record in list(self._recent_messages.items()):
            cached_at = self._float_or_default(record.get("cached_at"), now)
            if now - cached_at > MESSAGE_CACHE_TTL_SECONDS:
                self._recent_messages.pop(key, None)

    def _filter_recalled_records(self, event):
        self._ensure_recalled_record_ids()
        group_id = self._normalize_id(event.get_group_id())
        if not group_id:
            return list(self._recalled_messages)
        return [
            record
            for record in self._recalled_messages
            if record.get("group_id") == group_id
        ]

    def _build_recalled_message_chain(self, records):
        lines = ["最近记录的撤回消息："]
        for record in records:
            sent_at = self._format_timestamp(record.get("time"))
            sender = record.get("sender_name") or record.get("sender_id") or "未知用户"
            lines.append(
                "#{} {} {}({})".format(
                    record.get("record_id") or "?",
                    sent_at,
                    sender,
                    record.get("sender_id") or "未知",
                )
            )
        return [Plain("\n".join(lines))]

    def _ensure_recalled_record_ids(self):
        current_max = 0
        for record in self._recalled_messages:
            record_id = record.get("record_id")
            if record_id:
                try:
                    current_max = max(current_max, int(record_id))
                except (TypeError, ValueError):
                    pass
                continue
            record["record_id"] = self._next_recalled_record_id
            current_max = max(current_max, self._next_recalled_record_id)
            self._next_recalled_record_id += 1

        if self._next_recalled_record_id <= current_max:
            self._next_recalled_record_id = current_max + 1

    def _find_recalled_record(self, event, record_id):
        normalized_record_id = self._normalize_id(record_id)
        for record in self._filter_recalled_records(event):
            if self._normalize_id(record.get("record_id")) == normalized_record_id:
                return record
        return None

    def _format_timestamp(self, timestamp):
        timestamp = self._int_or_default(timestamp, 0)
        if timestamp <= 0:
            return "未知时间"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

    def _int_or_default(self, value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _float_or_default(self, value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _parse_positive_int(self, text):
        match = re.search(r"(\d+)", text or "")
        if not match:
            return 0
        value = int(match.group(1))
        return value if value > 0 else 0

    def _get_onebot_message(self, raw):
        message = self._raw_get(raw, "message")
        if message is None:
            message = self._raw_get(raw, "raw_message")
        return self._copy_onebot_message(message)

    def _copy_onebot_message(self, message):
        if message is None:
            return []
        if isinstance(message, (list, dict)):
            return copy.deepcopy(message)
        return str(message)

    def _extract_forward_ids(self, message):
        forward_ids = []
        for segment in self._iter_onebot_segments(message):
            if not self._is_forward_segment(segment):
                continue
            forward_id = self._extract_segment_data(segment).get("id")
            if forward_id:
                forward_ids.append(self._normalize_id(forward_id))

        if isinstance(message, str):
            forward_ids.extend(
                self._normalize_id(item)
                for item in re.findall(r"\[CQ:forward,[^\]]*id=([^,\]]+)", message)
                if item
            )

        return list(dict.fromkeys(forward_ids))

    def _iter_onebot_segments(self, message):
        if isinstance(message, list):
            for segment in message:
                if isinstance(segment, dict):
                    yield segment
        elif isinstance(message, dict):
            yield message

    def _is_forward_segment(self, segment):
        return self._normalize_id(segment.get("type")).lower() == "forward"

    def _extract_segment_data(self, segment):
        data = segment.get("data", {})
        return data if isinstance(data, dict) else {}

    def _record_has_forward(self, record):
        return bool(record.get("forward_ids") or record.get("forward_nodes"))

    async def _try_replay_with_onebot(self, event, record):
        if not self._has_onebot_api(event):
            return False

        group_id = self._normalize_id(event.get_group_id())
        onebot_message = self._copy_onebot_message(
            record.get("onebot_message") or record.get("message_str") or ""
        )

        if self._record_has_forward(record):
            normal_message = self._remove_forward_segments(onebot_message)
            if not self._is_empty_onebot_message(normal_message):
                await self._send_group_message(event, group_id, normal_message)

            nodes = copy.deepcopy(record.get("forward_nodes") or [])
            if not nodes:
                nodes = await self._load_forward_nodes(event, onebot_message)
                if nodes:
                    record["forward_nodes"] = copy.deepcopy(nodes)
            if not nodes:
                raise RuntimeError("未能展开合并转发内容，可能转发 ID 已失效。")

            await self._send_group_forward_message(event, group_id, nodes)
            return True

        if not self._is_empty_onebot_message(onebot_message):
            await self._send_group_message(event, group_id, onebot_message)
            return True
        return False

    def _replay_message_components(self, record):
        components = list(record.get("message") or [])
        if components:
            return components
        message_str = record.get("message_str") or ""
        return [Plain(message_str)] if message_str else []

    def _has_onebot_api(self, event):
        bot = getattr(event, "bot", None)
        if bot and callable(getattr(bot, "call_action", None)):
            return True
        api = getattr(bot, "api", None) if bot else None
        return bool(api and callable(getattr(api, "call_action", None)))

    async def _call_onebot_api(self, event, action, **params):
        bot = getattr(event, "bot", None)
        if bot and callable(getattr(bot, "call_action", None)):
            response = await bot.call_action(action, **params)
        else:
            api = getattr(bot, "api", None) if bot else None
            if not api or not callable(getattr(api, "call_action", None)):
                raise RuntimeError("当前 OneBot 适配器没有暴露 call_action。")
            response = await api.call_action(action, **params)

        self._raise_for_onebot_error(action, response)
        return response

    def _raise_for_onebot_error(self, action, response):
        if not isinstance(response, dict):
            return
        status = self._normalize_id(response.get("status")).lower()
        retcode = response.get("retcode")
        failed = status == "failed"
        if retcode is not None:
            try:
                failed = failed or int(retcode) != 0
            except (TypeError, ValueError):
                failed = True
        if not failed:
            return

        message = (
            response.get("wording")
            or response.get("msg")
            or response.get("message")
            or response.get("retcode")
        )
        raise RuntimeError(f"{action} 调用失败：{message}")

    async def _send_group_message(self, event, group_id, message):
        await self._call_onebot_api(
            event,
            "send_group_msg",
            group_id=self._onebot_id(group_id),
            message=message,
            auto_escape=False,
        )

    async def _send_group_forward_message(self, event, group_id, nodes):
        await self._call_onebot_api(
            event,
            "send_group_forward_msg",
            group_id=self._onebot_id(group_id),
            messages=nodes,
        )

    def _onebot_id(self, value):
        value = self._normalize_id(value)
        return int(value) if value.isdigit() else value

    def _is_empty_onebot_message(self, message):
        if message is None:
            return True
        if isinstance(message, str):
            return not message.strip()
        if isinstance(message, list):
            return not message
        return False

    def _remove_forward_segments(self, message):
        if isinstance(message, list):
            return [
                copy.deepcopy(segment)
                for segment in message
                if not (isinstance(segment, dict) and self._is_forward_segment(segment))
            ]
        if isinstance(message, dict):
            return [] if self._is_forward_segment(message) else [copy.deepcopy(message)]
        if isinstance(message, str):
            return re.sub(r"\[CQ:forward,[^\]]+\]", "", message).strip()
        return []

    async def _load_forward_nodes(self, event, message):
        nodes = []
        for segment in self._iter_onebot_segments(message):
            if not self._is_forward_segment(segment):
                continue
            nodes.extend(await self._load_segment_forward_nodes(event, segment))

        for forward_id in self._extract_forward_ids(message):
            has_forward_id = any(
                self._normalize_id(node.get("_source_forward_id")) == forward_id
                for node in nodes
            )
            if not has_forward_id:
                nodes.extend(await self._fetch_forward_nodes(event, forward_id))

        for node in nodes:
            node.pop("_source_forward_id", None)
        return nodes

    async def _load_segment_forward_nodes(self, event, segment):
        data = self._extract_segment_data(segment)
        inline_nodes = self._normalize_forward_nodes(
            data.get("content") or data.get("messages")
        )
        forward_id = self._normalize_id(data.get("id"))
        for node in inline_nodes:
            node["_source_forward_id"] = forward_id
        if inline_nodes:
            return inline_nodes
        if not forward_id:
            return []
        nodes = await self._fetch_forward_nodes(event, forward_id)
        for node in nodes:
            node["_source_forward_id"] = forward_id
        return nodes

    async def _fetch_forward_nodes(self, event, forward_id):
        first_error = None
        for params in ({"message_id": forward_id}, {"id": forward_id}):
            try:
                response = await self._call_onebot_api(
                    event,
                    "get_forward_msg",
                    **params,
                )
                nodes = self._normalize_forward_nodes(self._extract_data(response))
                if nodes:
                    return nodes
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error:
            raise first_error
        return []

    def _extract_data(self, response):
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response

    def _normalize_forward_nodes(self, data):
        if isinstance(data, dict):
            if self._looks_like_forward_node(data):
                messages = [data]
            else:
                messages = (
                    data.get("messages")
                    or data.get("message")
                    or data.get("content")
                    or []
                )
        elif isinstance(data, list):
            messages = data
        else:
            messages = []

        if isinstance(messages, dict):
            messages = [messages]
        if not isinstance(messages, list):
            messages = []

        nodes = []
        for item in messages:
            node = self._normalize_forward_node(item)
            if node:
                nodes.append(node)
        return nodes

    def _looks_like_forward_node(self, data):
        if self._normalize_id(data.get("type")).lower() == "node":
            return True
        return bool(
            any(key in data for key in ("content", "message", "raw_message", "id"))
            and any(
                key in data
                for key in ("sender", "user_id", "uin", "nickname", "name")
            )
        )

    def _normalize_forward_node(self, item):
        node_id = ""
        if isinstance(item, str):
            content = item
            node_data = {}
        elif isinstance(item, dict):
            if self._normalize_id(item.get("type")).lower() == "node":
                node_data = self._extract_segment_data(item)
            else:
                node_data = item
            node_id = self._normalize_id(
                node_data.get("id") or node_data.get("message_id")
            )
            content = (
                node_data.get("content")
                or node_data.get("message")
                or node_data.get("raw_message")
                or ""
            )
        else:
            return None

        content = self._copy_onebot_message(content)
        if self._is_empty_onebot_message(content):
            if node_id:
                return {"type": "node", "data": {"id": node_id}}
            return None

        sender = node_data.get("sender") if isinstance(node_data, dict) else {}
        if not isinstance(sender, dict):
            sender = {}

        user_id = (
            node_data.get("user_id")
            or node_data.get("uin")
            or sender.get("user_id")
            or sender.get("uin")
            or 0
        )
        nickname = (
            node_data.get("nickname")
            or node_data.get("name")
            or sender.get("nickname")
            or sender.get("card")
            or str(user_id)
        )
        return {
            "type": "node",
            "data": {
                "user_id": (
                    self._onebot_id(user_id) if self._normalize_id(user_id) else 0
                ),
                "nickname": self._normalize_id(nickname) or "未知用户",
                "content": content,
            },
        }

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
