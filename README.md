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
| `ops_get_legal` | 查询法律事件 | "这个专利现在有效吗？" |
| `ops_get_register` | EPO 登记簿 | "审查到哪一步了？" -主要适用于 EP 文献|
| `ops_get_images` | 查询可用附图元数据| "调取附图元信息"-当前工具不直接下载图片文件 |
| `ops_cpc_lookup` | CPC 分类层级查询 | "A01B 下面有什么子类？" |
| `ops_cpc_search` | CPC 关键词搜索 | "激光相关的 CPC 分类号？" |
| `ops_convert_number` | 专利号格式转换 | "把 CN 申请号转成 DOCDB 格式" |
| `ops_throttle_status` | 显示最近一次请求的限流信息 | 需先执行一次 OPS 请求；不直接计算剩余额度 |

## 前置条件

- **Python 3.10+**（推荐 3.12+，3.14 已验证）
- 支持本地 stdio MCP Server 的客户端，例如 Claude Code
- **EPO 开发者账号**（[免费注册](https://developers.epo.org)）

## 快速开始

### 1. 注册 EPO 并获取凭证

1. 访问 [developers.epo.org](https://developers.epo.org) 注册账号
2. 登录后进入 **My Apps** → **Add new App**
3. 选择 **OPS v3.2**，创建后获取 **Consumer Key** 和 **Consumer Secret**
4. 需注意官方说明书说明每个app只存在20分，过了20分钟需要另外建立一个app重新获得key和secret，为了便于替换key和secret，设置了"ops_credentials.example.json"文档，只需要把新的key和secret粘贴到该文档中，MCP设置会进行热更新。

### 2. 克隆仓库

```bash
git clone https://github.com/talenlin/epo-ops.git
cd epo-ops
```

### 3. 创建虚拟环境并安装依赖

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "mcp>=1.2,<2" "httpx>=0.27,<1"
```

#### Windows PowerShell

```powershell
py -m venv .venv
& .\.venv\Scripts\Activate.ps1
py -m pip install "mcp>=1.2,<2" "httpx>=0.27,<1"
```

## 配置凭证

推荐复制凭证模板，在本地文件中填写真实凭证。

### macOS / Linux

```bash
cp ops_credentials.example.json ops_credentials.json
```

### Windows PowerShell

```powershell
Copy-Item ops_credentials.example.json ops_credentials.json
```

编辑 `ops_credentials.json`：

```json
{
  "OPS_CONSUMER_KEY": "YOUR_KEY",
  "OPS_CONSUMER_SECRET": "YOUR_SECRET"
}
```

`ops_credentials.json` 已被 `.gitignore` 排除。提交代码前仍建议运行 `git status`，确认真实凭证没有进入待提交文件。

### 凭证读取优先级

Server 按以下顺序查找凭证：

1. `OPS_CREDENTIALS_FILE` 指向的自定义 JSON 文件
2. 与 `ops_mcp_server.py` 位于同一目录的 `ops_credentials.json`
3. 环境变量 `OPS_CONSUMER_KEY` 和 `OPS_CONSUMER_SECRET`

凭证会在每次工具调用时重新读取。修改凭证文件后，通常无需重启 MCP Server。

## 连通性测试

确保凭证已经配置，然后运行：

### macOS / Linux

```bash
python ops_mcp_server.py --test
```

### Windows PowerShell

```powershell
py .\ops_mcp_server.py --test
```

测试会依次检查身份认证、书目数据检索、专利搜索及最近一次请求返回的限流信息。实际响应大小和限流头会随时间、账号及 EPO 服务状态变化。

## 注册到 Claude Code

下面的配置使用用户级 scope，因此可以在多个项目中调用该 MCP Server。若只希望当前项目使用，可将 `--scope user` 改为 `--scope local`。

### macOS / Linux

在仓库根目录运行：

```bash
claude mcp add --scope user --transport stdio epo-ops -- \
  "$(pwd)/.venv/bin/python" "$(pwd)/ops_mcp_server.py"
```

### Windows PowerShell

在仓库根目录运行：

```powershell
$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$server = (Resolve-Path ".\ops_mcp_server.py").Path
claude mcp add --scope user --transport stdio epo-ops -- $python $server
```

检查注册结果：

```bash
claude mcp get epo-ops
claude mcp list
```

在 Claude Code 会话内运行 `/mcp`，连接成功后应看到 `epo-ops` 及 13 个工具。

## 使用示例

```text
帮我查询 EP1000000 的申请人、发明人和 CPC 分类。

查询 EP1676595 的 INPADOC 同族和法律事件，并区分事实记录与有效性判断。

搜索申请人为 IBM、标题或摘要涉及 semiconductor laser 的专利，返回前 10 条结果。

把一个原始格式的专利号转换为 DOCDB 格式。
```

复杂检索建议明确指定检索字段、文献号格式、结果范围和需要返回的字段。

## 项目结构

```text
epo-ops/
|-- ops_mcp_server.py
|-- ops_credentials.example.json
|-- ops_credentials.json            # 本地真实凭证，Git 已忽略
|-- .gitignore
|-- LICENSE
|-- README.md
`-- README-v2.md
```

## 常见问题

### `/mcp` 显示连接失败

1. 先运行 `ops_mcp_server.py --test`，确认凭证和 OPS 网络连接正常。
2. 运行 `claude mcp get epo-ops`，检查 Python 和脚本是否使用绝对路径。
3. 确认 MCP 配置中的 Python 环境已经安装 `mcp` 和 `httpx`。
4. 确认 `ops_credentials.json` 位于脚本目录，或其他凭证来源已正确配置。
5. 在终端中直接使用配置里的 Python 路径运行脚本，检查启动错误。

### Windows 找到了错误的 Python

Windows 可能同时存在 Python Launcher、Microsoft Store 执行别名及其他软件附带的 Python。推荐为本项目创建 `.venv`，并在 MCP 配置中使用：

```text
<仓库绝对路径>\.venv\Scripts\python.exe
```

查看当前解释器：

```powershell
py -c "import sys; print(sys.executable)"
```

### 修改凭证后没有生效

代码会在每次工具调用时重新读取凭证，但已经签发的访问令牌可能仍会短暂缓存。如果需要立即排查，可重新运行连通性测试或重启 MCP Server。

### 查不到中文摘要或全文

OPS 的内容和语言覆盖因国家/地区、文献类型及数据来源而异。查无结果不一定表示专利不存在。中文专利深度检索可配合国家知识产权局、Espacenet 或其他专业专利数据库交叉验证。

### 法律事件是否等于当前法律状态

不等同。`ops_get_legal` 返回的是法律事件记录。判断专利是否在特定国家、特定日期有效，通常还需要结合国家登记簿、年费、期限、异议、无效及权利恢复等信息，并在高风险场景下咨询专业人士。

## OPS 公平使用限制

根据 EPO 当前公布的 Fair Use Charter：

- OPS 免费数据量上限为每个日历周 4 GB
- 日历周按 GMT 计算，从周一 00:00 到周日 24:00
- OPS 和 European Publication Server 的最大流量约为 1 Mbit/s
- EPO 建议将自动批量任务安排在 GMT 19:00 至 07:00 或周末
- 限额和访问条件可能随运行情况调整

批量任务应控制并发和请求频率，并处理 HTTP 403、429、超时及临时服务故障。

官方说明：[EPO Fair Use Charter](https://www.epo.org/en/service-support/ordering/fair-use)

## 数据与责任说明

- 本工具返回的数据来自 EPO OPS，完整性和时效性受上游服务影响。
- 法律事件、登记簿和同族数据仅供检索与研究，不构成法律意见。
- `ops_get_images` 当前返回附图可用性及引用信息，不直接下载图片二进制文件。
- `ops_throttle_status` 仅显示最近一次 OPS 响应中提供的限流头，不代表精确剩余额度。
- 使用者应自行遵守 EPO OPS 条款、数据许可和适用法律。

## 技术栈

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [HTTPX](https://www.python-httpx.org/)
- [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops)

## License

本项目使用 [MIT License](LICENSE)。

## 相关资源

- [项目仓库](https://github.com/talenlin/epo-ops)
- [EPO Developer Portal](https://developers.epo.org/)
- [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops)
- [EPO Fair Use Charter](https://www.epo.org/en/service-support/ordering/fair-use)
- [Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io/)

