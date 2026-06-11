# EPO OPS MCP Server

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-stdio-green)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

让 Claude Code 通过自然语言直接检索全球专利数据。基于 EPO (欧洲专利局) OPS API v3.2，提供 13 个 MCP 工具，覆盖专利搜索、书目获取、同族查询、法律状态、CPC 分类等功能。

## 功能一览

| 工具 | 功能 | 示例 |
|------|------|------|
| `ops_search` | CQL 专利检索 | "搜索华为关于半导体的专利" |
| `ops_get_biblio` | 书目数据（100+ 字段） | "查 EP1000000 的发明人和分类号" |
| `ops_get_abstract` | 专利摘要 | "这个专利讲了什么？" |
| `ops_get_fulltext` | 说明书 / 权利要求全文 | "列出权利要求" |
| `ops_get_family` | INPADOC 扩展同族 | "这个专利在哪些国家申请了？" |
| `ops_get_equivalents` | DOCDB 简单同族 | "有哪些等效专利？" |
| `ops_get_legal` | 法律状态事件 | "这个专利现在有效吗？" |
| `ops_get_register` | EPO 登记簿 | "审查到哪一步了？" |
| `ops_get_images` | 附图信息 | "让我看看附图" |
| `ops_cpc_lookup` | CPC 分类层级查询 | "A01B 下面有什么子类？" |
| `ops_cpc_search` | CPC 关键词搜索 | "激光相关的 CPC 分类号？" |
| `ops_convert_number` | 专利号格式转换 | "把 CN 申请号转成 DOCDB 格式" |
| `ops_throttle_status` | 配额/限流状态 | "OPS 配额还剩多少？" |

## 前置条件

- **Claude Code 2.0+**（需支持 MCP 协议）
- **Python 3.10+**（推荐 3.12+，3.14 已验证）
- **EPO 开发者账号**（[免费注册](https://developers.epo.org)，审批约 1-3 工作日）

## 快速开始

### 1. 注册 EPO 并获取凭证

1. 访问 [developers.epo.org](https://developers.epo.org) 注册账号
2. 登录后进入 **My Apps** → **Add new App**
3. 选择 **OPS v3.2**，创建后获取 **Consumer Key** 和 **Consumer Secret**
4. ⚠️ Secret 只显示一次，立即保存

### 2. 安装

```bash
# 克隆仓库
git clone https://github.com/<你的用户名>/epo-ops-mcp.git
cd epo-ops-mcp

# 安装 Python 依赖
pip install mcp httpx

# 配置凭证（将 example 文件重命名并填入你的 Key/Secret）
cp ops_credentials.example.json ops_credentials.json
# 编辑 ops_credentials.json 填入真实凭证
```

### 3. 注册到 Claude Code

```bash
# macOS / Linux
claude mcp add -s user -t stdio epo-ops \
    -- python3 "$(pwd)/ops_mcp_server.py"

# Windows（必须使用完整 Python 路径！）
claude mcp add -s user -t stdio epo-ops \
    -- C:/Users/<用户名>/AppData/Local/Python/bin/python.exe "D:/path/to/epo-ops-mcp/ops_mcp_server.py"
```

> 💡 **为什么 Windows 要用完整路径？** 见下方 [常见问题](#windows-python-路径问题)。

### 4. 验证

```bash
# 连通性测试
python ops_mcp_server.py --test
```

成功输出：
```
=== EPO OPS MCP Server — Connectivity Test ===
[1/4] Authenticating...  [OK] Token obtained (28 chars)
[2/4] Fetching EP1000000 biblio...  [OK] Got 10949 bytes
[3/4] Searching 'pa=IBM'...  [OK] Got 1286 bytes
[4/4] Throttle status:  (search=green:15, retrieval=green:100)
=== All tests passed ===
```

重启 Claude Code 后 `/mcp` 应显示 **epo-ops** 及 13 个工具。

### 5. 使用

```
你：帮我查一下 EP1000000 的基本信息
你：EP1676595 现在有效吗？
你：公牛集团在轨道插座方面的专利有哪些？
```

## 凭证管理

本 Server 按以下优先级读取凭证：

1. `ops_credentials.json`（与脚本同目录）← **推荐**
2. 环境变量 `OPS_CONSUMER_KEY` / `OPS_CONSUMER_SECRET`
3. 环境变量 `OPS_CREDENTIALS_FILE`（指向自定义 JSON 路径）

**热加载**：编辑 `ops_credentials.json` 后无需重启 Claude Code，立即生效。

## 项目结构

```
epo-ops-mcp/
├── ops_mcp_server.py              # MCP Server 主程序
├── ops_credentials.example.json   # 凭证模板（发布用）
├── ops_credentials.json           # 真实凭证（Git 已忽略）
├── .gitignore
└── README.md
```

## 常见问题

### `/mcp` 显示 "Failed to reconnect: -32000"

1. 先跑 `--test` 确认 Server 本身正常
2. 检查 `~/.claude.json` 中 `command` 是否用了完整 Python 路径
3. 检查 `ops_credentials.json` 是否在脚本同目录下

### Windows Python 路径问题

Windows PATH 中常有多个 `python.exe`（微软商店重定向器、LibreOffice 内嵌等），Claude Code 可能命中错误的那个。

```bash
# 找到真正的 Python
python -c "import sys; print(sys.executable)"

# 关闭微软商店的 python.exe 别名
# Windows 设置 → 应用 → 应用执行别名 → 关闭 python.exe 和 python3.exe
```

### 中国专利摘要搜索不到

EPO OPS 对中文摘要的索引覆盖有限。对于中文专利深度检索，建议配合 PatSnap / 智慧芽 等数据库使用。epo-ops 优势在于欧洲专利精确查询、法律状态和同族检索。

### 更换凭证

编辑 `ops_credentials.json`，保存即生效。验证：

```bash
python ops_mcp_server.py --test
```

## API 配额

EPO OPS 有 Fair Use 限制：
- 小时配额约 450 MB
- 周配额每周一 UTC 午夜刷新
- 用 `ops_throttle_status` 随时查看

详见 [EPO Fair Use 政策](https://www.epo.org/service-support/ordering/fair-use.html)。

## 技术栈

- [FastMCP](https://github.com/modelcontextprotocol/python-sdk) — Python MCP SDK
- [httpx](https://www.python-httpx.org/) — 异步 HTTP 客户端
- [EPO OPS v3.2](https://developers.epo.org/apis/ops-v32) — REST API

## License

MIT

## 相关资源

- [EPO 开发者门户](https://developers.epo.org)
- [OPS API 文档](https://developers.epo.org/apis/ops-v32)
- [MCP 协议规范](https://modelcontextprotocol.io)
- [完整使用指南（中文）](./MCP使用指南-v1.1.md)
