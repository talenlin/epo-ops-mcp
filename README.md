# EPO OPS MCP Server

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-stdio-green)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

通过 MCP 客户端使用自然语言检索全球专利数据。本项目基于欧洲专利局（EPO）的 Open Patent Services（OPS）REST API v3.2，提供专利检索、书目数据、摘要、全文、专利同族、法律事件、EPO 登记簿、CPC 分类、专利号转换和配额监控等能力。

> 本项目是非官方社区工具，与欧洲专利局（EPO）没有隶属或认可关系。使用时须遵守 EPO OPS 的条款、配额和流量限制。

## 安装最新版

```bash
git clone https://github.com/talenlin/epo-ops-mcp.git
cd epo-ops-mcp
```

`main` 分支始终指向最新版。目前最新版为 v2，包含 14 个 MCP 工具。

## 历史版本


- v1：`v1.0.0`
- v2：`v2.0.0`

安装 v1：

```bash
git clone --branch v1.0.0 --depth 1 https://github.com/talenlin/epo-ops-mcp.git
cd epo-ops-mcp
```


## v2 功能变化

相对 v1，v2 主要增加：

- `ops_quota_monitor`：独立周配额监控工具。
- 增强 `ops_throttle_status`：在最近一次 OPS 响应头基础上，附带 EPO 周边界和重置时间。
- `--test` 连通性测试输出更完整的配额与周边界信息。
- 使用epo响应的access token进行连接，而access token自动更新

EPO 当前 Fair Use Charter 说明 OPS 免费数据量上限为每周 4 GB，周期为 GMT 周一 00:00 至周日 24:00。响应头中的 `X-RegisteredQuotaPerWeek-Used` 单位并非明确公开，因此 v2 对剩余额度仅提供辅助估算，不应作为精确计费依据。

## 工具一览

| 工具 | 功能 | 使用提示 |
|------|------|----------|
| `ops_search` | 使用 CQL 检索专利 | 例如按申请人、标题或分类号检索 |
| `ops_get_biblio` | 获取专利书目数据 | 包括申请人、发明人、分类号和优先权等 |
| `ops_get_abstract` | 获取专利摘要 | 摘要可用性取决于 OPS 数据覆盖 |
| `ops_get_fulltext` | 获取说明书或权利要求全文 | 全文可用性因文献和国家/地区而异 |
| `ops_get_family` | 获取 INPADOC 扩展同族 | 可选附带书目数据或法律事件 |
| `ops_get_equivalents` | 获取 DOCDB 简单同族 | 用于查询直接等效的专利文献 |
| `ops_get_legal` | 获取 INPADOC 法律事件 | 事件记录不应单独作为法律有效性结论 |
| `ops_get_register` | 获取 EPO 登记簿程序数据 | 主要适用于 EP 文献 |
| `ops_get_images` | 查询可用附图的元数据 | 当前工具不直接下载图片文件 |
| `ops_cpc_lookup` | 查询 CPC 分类层级 | 支持祖先、导航和深度参数 |
| `ops_cpc_search` | 按关键词搜索 CPC 分类 | 可用于辅助确定检索分类号 |
| `ops_convert_number` | 转换专利号格式 | 支持 original、DOCDB 和 epodoc 等格式 |
| `ops_throttle_status` | 显示最近一次请求的限流信息 | v2 附带 EPO 周边界和重置时间 |
| `ops_quota_monitor` | 周配额监控 | 提供周额度、最近用量、重置倒计时和说明 |

## 前置条件

- Python 3.10 或更高版本
- 支持本地 stdio MCP Server 的客户端，例如 Claude Code
- EPO 开发者账号及 OPS Consumer Key / Consumer Secret

EPO 开发者门户：[https://developers.epo.org](https://developers.epo.org/)

## 快速开始

### 1. 创建虚拟环境并安装依赖

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "mcp>=1.2,<2" "httpx>=0.27,<1"
```

Windows PowerShell:

```powershell
py -m venv .venv
& .\.venv\Scripts\Activate.ps1
py -m pip install "mcp>=1.2,<2" "httpx>=0.27,<1"
```

### 2. 配置凭证

macOS / Linux:

```bash
cp ops_credentials.example.json ops_credentials.json
```

Windows PowerShell:

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

macOS / Linux:

```bash
python ops_mcp_server.py --test
```

Windows PowerShell:

```powershell
py .\ops_mcp_server.py --test
```

测试会依次检查身份认证、书目数据检索、专利搜索及最近一次请求返回的限流信息。实际响应大小和限流头会随时间、账号及 EPO 服务状态变化。

## 注册到 Claude Code

下面的配置使用用户级 scope，因此可以在多个项目中调用该 MCP Server。若只希望当前项目使用，可将 `--scope user` 改为 `--scope local`。

macOS / Linux:

```bash
claude mcp add --scope user --transport stdio epo-ops-v2 -- \
  "$(pwd)/.venv/bin/python" "$(pwd)/ops_mcp_server.py"
```

Windows PowerShell:

```powershell
$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$server = (Resolve-Path ".\ops_mcp_server.py").Path
claude mcp add --scope user --transport stdio epo-ops-v2 -- $python $server
```

检查注册结果：

```bash
claude mcp get epo-ops-v2
claude mcp list
```

在 Claude Code 会话内运行 `/mcp`，连接成功后应看到 `epo-ops-v2` 及 14 个工具。

## 使用示例

```text
帮我查询 EP1000000 的申请人、发明人和 CPC 分类。

查询 EP1676595 的 INPADOC 同族和法律事件，并区分事实记录与有效性判断。

搜索申请人为 IBM、标题或摘要涉及 semiconductor laser 的专利，返回前 10 条结果。

查看本周 OPS 配额使用情况和下次重置时间。
```

复杂检索建议明确指定检索字段、文献号格式、结果范围和需要返回的字段。

## 项目结构

```text
epo-ops-mcp/
|-- ops_mcp_server.py
|-- ops_credentials.example.json
|-- ops_credentials.json            # 本地真实凭证，Git 已忽略
|-- .gitignore
|-- LICENSE
|-- docs/
|   `-- README-v1.md                # v1 说明归档
`-- README.md
```

## 常见问题

### `/mcp` 显示连接失败

1. 先运行 `ops_mcp_server.py --test`，确认凭证和 OPS 网络连接正常。
2. 运行 `claude mcp get epo-ops-v2`，检查 Python 和脚本是否使用绝对路径。
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
- `ops_throttle_status` 仅显示最近一次 OPS 响应中提供的限流头和周边界信息，不代表精确剩余额度。
- `ops_quota_monitor` 基于 EPO 周配额和最近一次响应头做辅助估算，不代表官方账单或精确限额。
- 使用者应自行遵守 EPO OPS 条款、数据许可和适用法律。

## 技术栈

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [HTTPX](https://www.python-httpx.org/)
- [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops)

## License

本项目使用 [MIT License](LICENSE)。

## 相关资源

- [项目仓库](https://github.com/talenlin/epo-ops-mcp)
- [EPO Developer Portal](https://developers.epo.org/)
- [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops)
- [EPO Fair Use Charter](https://www.epo.org/en/service-support/ordering/fair-use)
- [Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io/)
