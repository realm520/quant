# CEXTools 文档中心

## 📚 核心文档

| 文档 | 说明 |
|------|------|
| [cextools-usage.md](cextools-usage.md) | CEXTools 使用指南（命令与示例） |
| [DEPLOYMENT_MACOS.md](DEPLOYMENT_MACOS.md) | 在 macOS 上部署 |
| [DEPLOYMENT_LINUX.md](DEPLOYMENT_LINUX.md) | 在 Linux 上部署 |
| [UV_GIT_EXECUTION.md](UV_GIT_EXECUTION.md) | 使用 uv + Git 路径直接执行 |
| [architecture.md](architecture.md) | 架构说明 |

---

## 🚀 快速开始
- 首次使用：阅读 [cextools-usage.md](cextools-usage.md)
- 本地部署：参考 [DEPLOYMENT_MACOS.md](DEPLOYMENT_MACOS.md) 或 [DEPLOYMENT_LINUX.md](DEPLOYMENT_LINUX.md)
- 无需安装：直接使用 [UV_GIT_EXECUTION.md](UV_GIT_EXECUTION.md)

---

## 🔧 常见问题（节选）
- PEP 668（externally-managed-environment）：使用虚拟环境或 uv 避免系统 Python 限制
- 数据库连接失败：检查 `DATABASE_URL` 用户/主机/端口与库初始化
- XT listen key 403：接口时间漂移所致，程序自动重试

---

## 🔗 外部链接
- XT API 文档: https://doc.xt.com
- 项目仓库: https://github.com/realm520/quant
