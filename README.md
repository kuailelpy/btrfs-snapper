# Btrfs Snapper

Btrfs 文件系统快照管理工具，提供 Web UI 界面进行可视化操作。

## 功能特性

- 📸 **快照管理** - 创建、删除、查看 Btrfs 快照
- 📁 **子卷支持** - 支持对子卷创建快照
- ⏰ **定时任务** - 支持按日、周、月自动创建快照
- 🔗 **Latest 链接** - 自动更新最新快照符号链接
- 🧹 **自动清理** - 支持设置最大保留数量，自动清理旧快照
- 📋 **执行记录** - 记录所有手动和自动操作历史
- 🔒 **用户认证** - 支持账户创建和登录保护

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/kuailelpy/btrfs-snapper.git
cd btrfs-snapper
```

### 2. 安装依赖

```bash
pip install flask apscheduler bcrypt
```

### 3. 初始化配置

```bash
# 复制配置文件模板
cp config.example.json config.json

# 编辑配置文件（可选）
nano config.json
```

### 4. 运行

```bash
python3 app.py
```

访问 http://localhost:5003

## 系统服务部署

```bash
# 复制服务文件到系统目录
cp 服务/btrfs-snapper.service /etc/systemd/system/

# 重新加载 systemd
systemctl daemon-reload

# 启动服务
systemctl start btrfs-snapper

# 设置开机自启
systemctl enable btrfs-snapper
```

## 配置文件说明

首次使用前，请复制 `config.example.json` 为 `config.json`：

```bash
cp config.example.json config.json
```

配置文件包含以下字段：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `max_storage_mb` | 执行记录存储上限 (MB) | 100 |
| `scheduled_tasks` | 定时任务列表 | [] |
| `manual_records` | 手动操作记录 | [] |
| `auto_records` | 自动操作记录 | [] |

**注意**：`config.json` 已被 `.gitignore` 忽略，不会提交到 Git，请放心配置您的个人信息。

## 使用说明

### 首次使用

1. 打开 Web 界面
2. 创建管理员账户
3. 登录后开始使用

### 创建快照

1. 选择 Btrfs 分区
2. 选择源子卷（可选）
3. 选择快照保存目录
4. 设置快照名称
5. 点击"创建快照"

### 设置定时任务

1. 切换到"定时任务"标签
2. 填写任务名称、选择分区
3. 设置执行频率（每天/每周/每月）
4. 设置保留数量（0 表示不限制）
5. 点击"创建任务"

### 忘记密码

如需重置密码，请删除服务器上的密码目录：

```bash
rm -rf /DATA/AppData/Btrfs-snapper/password
```

然后重新访问 Web 界面创建新账户。

## 目录结构

```
btrfs-snapper/
├── app.py                  # 主程序
├── config.example.json     # 配置文件模板
├── config.json             # 实际配置文件（.gitignore 忽略）
├── templates/              # HTML 模板
│   ├── index.html
│   └── login.html
├── 服务/                   # 系统服务文件
│   └── btrfs-snapper.service
├── logs/                   # 日志目录（.gitignore 忽略）
├── records/                # 执行记录目录（.gitignore 忽略）
└── password/               # 密码文件目录（.gitignore 忽略）
```

## 注意事项

- 本工具需要在 root 权限下运行（Btrfs 操作需要）
- 请确保系统已安装 `btrfs-progs` 包
- 建议定期备份 `config.json` 文件

## License

MIT
