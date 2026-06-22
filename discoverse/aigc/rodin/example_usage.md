# Rodin 3D模型生成工具使用示例

## 📋 功能概览

本工具支持批量提交3D生成任务和异步下载，适合大规模自动化AIGC场景。

## text-to-3d

1. 准备prompt：编辑`prompt.txt`文件，使用英文，示例如下：

```
A chair. A wooden dining chair with a straight backrest, four legs, and seat edges suitable for gripping.
A pot. A stainless steel kitchen pot with two side handles, a removable lid, and a flat base.
A bottle. A plastic water bottle with a screw-on cap, cylindrical body, and narrow neck for stable holding.
```

2. 提交任务并下载
```bash
#  批量提交生成任务
export RODIN_API_KEY=your_api_key_here
python workflow_text-to-3d.py

# 稍等（单个任务约1-3分钟）检查并下载完成的模型
python workflow_text-to-3d.py -d
```

## image-to-3d

1. 准备yaml配置文件（见下方示例）
2. 提交任务：

```bash
export RODIN_API_KEY=your_api_key_here
python workflow_image-to-3d.py --config image_to_3d_tasks.yaml
```

3. 下载任务：

```bash
python workflow_image-to-3d.py -d --config image_to_3d_tasks.yaml
```

### Rodin image-to-3d YAML配置示例

```yaml
# image_to_3d_tasks.yaml

# 情况一：单张图片
- image: images/test1/1.png
  prompt: "a robot" # 可选

# 情况三：图片目录
- images: images/test1
  prompt: "a robot in a scene" # 可选

# 情况三：视频文件（video字段，frames为截图张数）
- video: videos/demo.mp4
  frames: 3
  prompt: "a robot from video" # 可选

```

参数说明
- 无参数（默认）：仅提交任务，不下载
- `-d` 或 `--download`：仅下载已完成任务，不提交新任务
- `--config`：指定yaml配置文件（仅image-to-3d脚本需要）