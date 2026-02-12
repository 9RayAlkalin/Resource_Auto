# Resource_Auto

一个用于从 Phigros 游戏中提取、处理和分析资源的自动化工具链。

## 项目简介

这个项目提供了一个完整的工具链，用于从 Phigros 游戏的 APK 文件中提取各种资源（谱面、插图、音乐、头像等），并将它们转换为可在 Phira 模拟器中使用的格式。工具还支持生成封面图像和渲染谱面视频。

## 功能特性

### 核心功能
- ✅ 从 APK 文件提取游戏元数据
- ✅ 提取多种资源类型（谱面、插图、音乐、头像）
- ✅ 将资源打包为 [Phira](https://github.com/TeamFlos/phira) 模拟器可用格式
- ✅ 自动生成美化封面图像
- ✅ 增量更新支持，只提取新内容
- ✅ 多线程处理，提高提取速度

### 扩展功能
- ✅ 自动检查版本更新（通过 TapTap API）
- ✅ 支持 FSB5 音频格式转换
- ✅ 可配置的处理流程
- ✅ 与 [Phi Recorder](https://github.com/2278535805/Phi-Recorder) 联动渲染视频

## 环境要求

### 系统要求
- Python 3.9 或更高版本
- macOS / Windows / Linux
- 至少 2GB 可用内存
- 建议 10GB 以上可用磁盘空间

### Python 依赖
```bash
pip install -r requirements.txt
```

主要依赖包：

- UnityPy: `1.10.18` - 读取 Unity 游戏资源
  - 一定要用`1.10.18`这个版本，否则会出现UnityTypeTree无法使用的问题！！！(其实是使用方式换了但是我懒得改😋)
- fsb5: 处理 FSB5 音频格式
- wget: 文件下载
- tqdm: 进度条显示
- Pillow: 图像处理
- pywebview: GUI 渲染（已弃用，使用 PIL 版本）
- libvorbis：输出ogg格式的音频
  - 你说的对但是我只知道macOS可以用`brew install libvorbis`安装😂😂😂

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/2278535805/Resource_Auto
cd Resource_Auto
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置设置

编辑 config.ini 文件，根据需要调整设置：

```ini
[TYPES]
avatar = True
Chart = True
Illustration = True
music = True

[SETTING]
autoUpdate = False
autoDownload = False
autoCover = True
autoRender = False
```

### 4. 运行主程序

```bash
python main.py
```

## 详细使用说明

### 基本流程

1. **输入版本号**：程序会询问当前版本号
2. **自动更新检查**：如果启用，会检查 TapTap 上的新版本
3. **下载 APK**：自动或手动下载游戏 APK
4. **提取元数据**：从 APK 提取游戏信息
5. **提取资源**：根据配置提取各种资源文件
6. **格式转换**：转换为 Phira 模拟器格式
7. **可选处理**：生成封面、渲染视频等

### 手动运行各模块

```bash
# 仅提取游戏信息
python gameInformation.py Phigros_3.10.1.apk output_dir

# 仅提取资源
python getResource.py Phigros_3.10.1.apk output_dir

# 仅打包为 Phira 格式
python phira.py output_dir

# 仅处理单张图片
python autoImage.py input.png output.png
```

## 配置文件说明

`config.ini` 详解

[TYPES] 部分

控制要提取的资源类型：

· `avatar`: 玩家头像
· `Chart`: 谱面文件（JSON）
· `Illustration`: 高清插图
· `IllustrationBlur`: 模糊版插图
· `IllustrationLowRes`: 低分辨率插图
· `music`: 音乐文件

[UPDATE] 部分

控制增量更新的数量：

· `main_story`: 保留的主线歌曲数量
· `side_story`: 保留的支线歌曲数量
· `other_song`: 保留的其他歌曲数量

[SETTING] 部分

程序行为设置：

· `outputCsv`: 是否输出 CSV 格式
· `autoUpdate`: 自动检查更新
· `autoDownload`: 自动下载 APK
· `autoCover`: 自动生成封面
· `autoRender`: 自动渲染视频
· `phiRender`: Phi Recorder 应用路径
· `AT/IN/HD/EZ`: 处理哪些难度等级

## 目录结构

```
Resource_Auto/
├── main.py                 # 主控制脚本
├── config.ini              # 配置文件
├── requirements.txt        # 依赖列表
├── gameInformation.py      # 提取游戏元数据
├── getResource.py          # 提取具体资源
├── phira.py                # 打包为 Phira 可用格式
├── autoImage.py            # 封面生成工具
├── taptap.py               # TapTap API 交互
├── ttools.py               # 外部工具接口
├── LICENSE                 # 开放源代码许可
└── README.md               # 说明文档
```

### 输出目录结构

程序运行后会产生以下目录结构：

```
data/                    # 版本号目录
├── difficulty.json        # 难度数据
├── info.json              # 歌曲信息
├── collection.json        # 收集品信息
├── avatar.json            # 头像信息
├── tips.txt               # 游戏提示
├── avatar/                # 头像图片
├── Illustration/          # 高清插图
├── IllustrationBlur/      # 模糊插图
├── IllustrationLowRes/    # 低分辨率插图
├── Chart_EZ/              # EZ难度谱面
├── Chart_HD/              # HD难度谱面  
├── Chart_IN/              # IN难度谱面
├── Chart_AT/              # AT难度谱面
├── music/                 # 音乐文件
├── phira/                 # Phira 格式文件
│   ├── EZ/
│   ├── HD/
│   ├── IN/
│   └── AT/
└── output/                # 最终输出
    ├── Cover/             # 生成的封面
    ├── EZ/                # 渲染的视频
    ├── HD/
    ├── IN/
    └── AT/
```

## 各模块详细说明

1. `gameInformation.py`

从 APK 中提取游戏的基础信息，包括歌曲列表、难度数据、收集品信息和头像数据。使用 UnityPy 库解析 Unity 资源文件。

2. `getResource.py`

核心资源提取模块，支持多线程处理，可以提取：

· 谱面：JSON 格式的谱面数据
· 插图：PNG 格式的游戏插图
· 音乐：FSB5 格式转换为 OGG
· 头像：玩家头像图片

3. `phira.py`

将提取的资源打包为 Phira 模拟器可用的格式，支持两种模式：

· ZIP 压缩格式（.pez 文件）
· 解压的文件夹格式

4. `autoImage.py`

图像处理工具，为谱面生成统一的封面图像。修复了原 `autoImage.py` 在 macOS 上的线程问题，使用纯 PIL 实现。

5. `taptap.py`

与 TapTap API 交互，获取最新的游戏版本信息和下载链接。

6. `ttools.py`

与外部工具 Phi Recorder 联动，用于渲染谱面演示视频。

## 高级配置

### 增量更新配置

在 `config.ini` 的 `[UPDATE]` 部分设置保留的歌曲数量：

· 设置为 0 表示提取全部
· 设置为正数表示只保留最新的 N 首歌曲

### 自定义处理流程

通过修改 `main.py` 可以自定义处理顺序：

```python
# 禁用某个步骤
if not setting.getboolean("autoCover"):
    # 跳过封面生成
    pass
```

### 扩展支持的游戏版本

程序默认支持 Phigros，但理论上可以修改用于其他 Unity 游戏 **(存疑? )** ：

1. 修改 `taptap.py` 中的游戏 ID
2. 调整资源路径规则
3. 可能需要修改 Unity 资源解析逻辑

## 故障排除

### 常见问题

**Q1: 运行时出现 "ModuleNotFoundError"**

A: 确保安装了所有依赖：`pip install -r requirements.txt`

**Q2: 提取资源时内存不足**

A: 减少同时处理的资源类型，或使用增量更新减少处理量

**Q3: 音频文件无法播放**

A: 确保安装了必要的音频编解码器，或检查 FSB5 转换是否正确

**Q4：提取资源时报错卡死**

A：确保已安装 libvorbis

### 调试模式

可以通过添加调试输出或修改日志级别来排查问题：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 注意事项

### 法律声明

1. 本工具仅用于学习和研究目的
2. 请勿将提取的资源用于商业用途
3. 尊重游戏开发者的知识产权
4. 使用本工具产生的任何后果由使用者自行承担

### 性能建议

1. SSD 硬盘可以显著提高提取速度
2. 处理大量资源时建议增加 Python 内存限制
3. 网络不稳定时建议手动下载 APK

### 兼容性说明

1. 主要针对 Phigros 游戏设计
2. 不同游戏版本可能需要调整参数
3. 音频处理依赖特定的 FSB5 版本

## 贡献指南

欢迎提交 **Issue** 和 **Pull Request** 来改进这个项目：

1. Fork 本仓库
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

### 许可证

本项目采用 **GNU General Public License 3.0** 许可证。详见 [LICENSE](LICENSE) 文件。

### 致谢

- 感谢 UnityPy 及 AssetStudio 项目的开发者
- 感谢 [TeamFlos](https://github.com/TeamFlos) 开发的 [Phira](https://github.com/TeamFlos/phira) 模拟器
- 感谢 [HLMC](https://github.com/2278535805) 开发的 [Phi-Recorder](https://pr.xhsr.org.cn) 渲染器
- 感谢所有贡献者

---