# 给 AI 的配置手册：用户说「请帮我验证 B站动态记忆桥 的功能是否可用，并配置好」时，照这份做

这份文件是给**接手配置的 AI**看的，不是给普通用户看的。目标只有一个：
让 QQ 里的机器人（AstrBot）达到「能收 B站 推荐私信、能解析用户分享的视频、能回答最近刷到什么」的状态。

整份流程约 4 步，改配置 → 重启 → 验证 → 收尾。**别跳步**，尤其别跳过「重启」。

---

## 0. 先定位这几处路径

| 东西 | 位置 |
| --- | --- |
| AstrBot 根目录 | 含 `data/plugins` 的那个目录（用运行中进程的 cwd 确认） |
| 本插件 | `<AstrBot>/data/plugins/astrbot_plugin_bili_bridge/` |
| 插件配置 | `<AstrBot>/data/config/astrbot_plugin_bili_bridge_config.json` |
| 同步状态 | `<AstrBot>/data/plugin_data/astrbot_plugin_bili_bridge/state.json` |
| 私信状态 | 同目录 `dm-state.json`（没有＝私信转发还没跑过） |
| 挑选结果 | `~/.dsh/bili-duty/digest/YYYY-MM.md`（DSH 侧 bili-scroll 写的） |

> AstrBot 一般是 Python 进程；改完配置要**重启它**（`python main.py` 重新拉），
> 因为配置只在 import/initialize 时读一次。

---

## 1. 三个前置依赖自检（缺哪个就让用户去装）

```powershell
# ① bili-cli：必须能返回 mid，说明已扫码登录
<python> -m pip show bili-agent
bili me show

# ② MemoryCompanion：目录在、日志有 loaded
Test-Path <AstrBot>/data/plugins/astrbot_plugin_memory_companion

# ③ bili-scroll：digest 目录里至少有一个当月文件
Get-ChildItem ~/.dsh/bili-duty/digest
```

缺 ①：`pip install bili-agent`，然后 `bili auth login` 让用户扫码。
缺 ②：装 `astrbot_plugin_memory_companion`（应用市场搜「我会牢牢记住你」）。
缺 ③：装 DSH 的 `dsh-bili-scroll`，跑一轮让它写出 digest。

---

## 2. 改配置（下面这些键，一项都别漏）

先备份，再改（`utf-8-sig` 读写，别把中文写坏）：

```json
{
  "bili_executable": "<bili 的绝对路径，例如 C:\\Python312\\Scripts\\bili.exe>",
  "owner_uids": "<用户 QQ 号>",
  "memory_user_ids": "<同上>",
  "sync_enabled": true,
  "sync_interval": 120,

  "dm_forward_enabled": true,
  "dm_owner_uid": "<收信方 B站 UID>",
  "dm_direction": "me",
  "dm_only_video": true,
  "dm_poll_interval": 120
}
```

逐个为什么：

- **`bili_executable` 用绝对路径**：AstrBot 进程的 PATH 未必有 Scripts 目录，写 `bili` 会偶发「用不了」。
- **`owner_uids` 必填**：空着等于谁都能触发解析。
- **`dm_forward_enabled` 默认是 false**，不打开就永远收不到私信——这是最常见的「装完没反应」。
- **`dm_owner_uid` 填「收信方」**（被推荐的那个人），不是登录号自己。
- **`dm_direction` 填 `me`**：刷视频工具用「登录 bili-cli 的那个号」给主人发推荐，消息在会话里是 `from: me`。
  拿不准就让用户跑一次 `bili dm read <dm_owner_uid> --limit 5`，看那批要转的消息是 `me` 还是 `them`。
- **`dm_target_session` 可以留空**：插件会按平台真实 id 自动拼成 `<平台id>:FriendMessage:<第一个 owner_uid>`。
  填了但对不上平台 id 也会自动纠正，不用纠结。

改完 **重启 AstrBot**。

---

## 3. 验证（按这个顺序，每步都要过）

1. **启动日志**里应该有这几行（搜关键字）：
   - `[BiliBridge] 私信转发已开：...`
   - `[BiliBridge] 已启动（同步=True...）`
   - `[BiliBridge] 已同步 B站 近况（N 字，来源 digest:...）`
   - `[BiliBridge] 私信转发：已记录基线 seqno=...（这批 me=X 条 / them=Y 条，当前只转 me）`

2. **让用户在 QQ 私聊发 `/bili_doctor`**，逐项要 ✅：
   - bili-cli 可用（带登录昵称）
   - 挑选结果可读：N 行可用
   - MemoryCompanion 在线
   - 触发白名单是你的 QQ
   - 私信转发：开，方向 me
   - 上次同步：成功/跳过 + 原因

3. **端到端测一次私信转发**（不用等用户）：
   ```powershell
   bili dm send <dm_owner_uid> "【转发测试】链路验证 https://www.bilibili.com/video/BV1xxxxxxxxx"
   ```
   等一个轮询周期（`dm_poll_interval`），日志出现 `私信转发：1 条私信 → QQ（共 1 次）` 即通过；
   用户 QQ 上会收到以「📬 B站 私信」开头的一条。

4. **测「最近刷到什么」**：让用户在 QQ 问「今天刷到什么」，应返回带编号的清单（插件自己答，不经过模型）。

5. **测「第一个视频讲了什么」**：应解析到最近推送清单里的第 1 条（日志有 `第 1 个 → BV...（来源 push）`），
   而不是记忆块里另一份排列的第 1 条。

---

## 4. 已知坑（照着避）

| 现象 | 原因 / 处理 |
| --- | --- |
| 有 digest 文件但不同步、日志干净 | 0.4.0 及更早的正则只认行首日期；0.4.1 起容忍 `- ` / `* ` / `1. ` 前缀。老版本手动改 `DIGEST_LINE_RE` |
| 私信一条都不转 | `dm_forward_enabled` 没开 / `dm_owner_uid` 空 / `dm_direction` 填反（大多数是填了 `them`） |
| 第一次上线没补发历史 | 设计如此：首次只记基线。要补发就临时删 `dm-state.json` 的 `last_seqno`（会重放最近 20 条） |
| 私信收到了但没转 | `dm_only_video=true` 时只转带 BV/视频链接的消息，寒暄会被跳过 |
| 改完配置没反应 | 没重启 AstrBot |
| 「第几个视频」答错 | 0.4.1 起按「最近推送顺序」解析；确认 `dm-state.json` 里有 `pushBvs` |
| `bili dm read` 报错 | bili-cli 没登录，或 UID 填的是登录号自己 |

---

## 5. 收尾：告诉用户现在能干什么

1. B站 推的视频私信会自动转到 QQ（想关就把 `dm_forward_enabled` 关掉）
2. 直接把 B站 视频链接/卡片发给她，她会拉字幕讲内容
3. 问她「今天刷到什么」能拿到最近清单；问「第 N 个讲了什么」会讲对应那条
