> 本项目代码由 OpenClaw AI 工具生成

# Btrfs Snapper

一个基于 Web 的 Btrfs 文件系统快照管理工具，提供直观的界面来创建、管理和监控 Btrfs 快照。

## 功能特性

- **分区管理**: 自动检测系统中的 Btrfs 分区
- **快照操作**: 创建、删除、查看快照
- **定时任务**: 支持每日、每周、每月自动创建快照
- **快照保留策略**: 可设置最大保留数量，自动清理旧快照
- **只读快照**: 支持创建只读快照保护数据
- **执行记录**: 记录所有手动和自动操作的详细日志
- **用户认证**: 基于 bcrypt 的安全登录系统，支持账户锁定保护
- **Latest 链接**: 自动更新最新快照的符号链接

## 技术栈

- **后端**: Python + Flask
- **前端**: HTML + JavaScript (原生)
- **任务调度**: APScheduler
- **密码加密**: bcrypt

## 安装

### 环境要求

- Python 3.7+
- Btrfs 文件系统
- Linux 系统（需要 btrfs-progs）

### 安装步骤

1. 克隆仓库
```bash
git clone https://github.com/YOUR_USERNAME/Btrfs-snapper.git
cd Btrfs-snapper
```

2. 安装依赖
```bash
pip install flask bcrypt apscheduler
```

3. 配置数据目录（默认: `/DATA/AppData/Btrfs-snapper`）

4. 运行应用
```bash
python app.py
```

应用将在 `http://0.0.0.0:5003` 启动。

### 系统服务部署

将 `服务/btrfs-snapper.service` 复制到 `/etc/systemd/system/`，然后：

```bash
sudo systemctl daemon-reload
sudo systemctl enable btrfs-snapper
sudo systemctl start btrfs-snapper
```

## 使用说明

### 首次使用

1. 打开 Web 界面
2. 创建管理员账户
3. 登录后管理 Btrfs 快照

### 创建快照

1. 选择目标分区
2. 选择子卷（可选）
3. 选择保存目录
4. 输入快照名称
5. 点击创建

### 定时任务

1. 进入"定时任务"标签
2. 填写任务名称、选择分区
3. 设置执行频率（每天/每周/每月）
4. 设置保留数量（0 表示不限制）
5. 创建任务

## 目录结构

```
Btrfs-snapper/
├── app.py              # 主应用文件
├── config.json         # 配置文件
├── templates/          # HTML 模板
│   ├── index.html      # 主界面
│   └── login.html      # 登录界面
├── 服务/               # 系统服务文件
│   └── btrfs-snapper.service
├── logs/               # 日志目录
└── records/            # 记录目录
```

## 配置说明

配置文件 `config.json`：

```json
{
  "max_storage_mb": 100,      # 记录存储上限 (MB)
  "scheduled_tasks": [],      # 定时任务列表
  "manual_records": [],       # 手动操作记录
  "auto_records": []          # 自动任务记录
}
```

## 安全特性

- 密码使用 bcrypt 加密存储
- 登录失败 5 次锁定 1 小时
- 登录失败 10 次锁定 24 小时
- Session 基于随机密钥

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！

## 免责声明

本工具直接操作文件系统，使用前请确保已备份重要数据。作者不对因使用本工具造成的数据丢失负责。
