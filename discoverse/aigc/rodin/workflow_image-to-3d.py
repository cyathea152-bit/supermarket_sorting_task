import os
import sys
import yaml
import argparse

try:
    from .workflow_common import (
        RODIN_API_KEY,
        API_ENDPOINT,
        create_session, 
        save_task_info, 
        download_only_mode
    )
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from workflow_common import (
        RODIN_API_KEY,
        API_ENDPOINT,
        create_session, 
        save_task_info, 
        download_only_mode
    )

def extract_frames_from_video(video_path, num_frames):
    import os
    import cv2
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0 or num_frames <= 0:
        cap.release()
        return []
    step = max(1, total_frames // num_frames)
    frame_indices = [i * step for i in range(num_frames)]
    # 生成输出目录：与视频同目录、同名（无扩展名）
    video_dir = os.path.dirname(video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.join(video_dir, video_name)
    os.makedirs(out_dir, exist_ok=True)
    saved_paths = []
    for idx, frame_idx in enumerate(frame_indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue
        out_path = os.path.join(out_dir, f"frame_{idx+1:03d}.png")
        cv2.imwrite(out_path, frame)
        saved_paths.append(out_path)
    cap.release()
    return saved_paths

def resolve_image_paths(task):
    # 单张图片
    if 'image' in task:
        return [task['image']]
    # 图片目录
    if 'images' in task:
        image_dir = task['images']
        return [os.path.join(image_dir, fname) for fname in sorted(os.listdir(image_dir)) if fname.lower().endswith(('.png', '.jpg', '.jpeg'))]
    # 视频
    if 'video' in task:
        video_path = task['video']
        num_frames = int(task.get('frames', 8))
        return extract_frames_from_video(video_path, num_frames)
    raise ValueError('任务配置必须包含 image, images 或 video 字段')

def get_image_mime_type(image_path):
    """根据文件扩展名返回对应的MIME类型"""
    ext = os.path.splitext(image_path)[1].lower()
    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
    }
    return mime_types.get(ext, 'image/png')  # 默认使用png

def generate_3d_asset_from_images(image_paths, prompt=None, session=None):
    if session is None:
        session = create_session()
    headers = {
        "Authorization": f"Bearer {RODIN_API_KEY}",
    }
    files = []
    for img_path in image_paths:
        mime_type = get_image_mime_type(img_path)
        files.append(('images', (os.path.basename(img_path), open(img_path, 'rb'), mime_type)))
    if prompt:
        files.append(('prompt', (None, prompt)))
    files.append(('geometry_file_format', (None, 'obj')))
    files.append(('quality', (None, 'medium')))
    response = session.post(
        API_ENDPOINT,
        headers=headers,
        files=files,
        timeout=(10, 60)
    )
    response_data = response.json()
    if response.status_code == 201:
        print(f"✅ API调用成功，状态码: {response.status_code}")
    else:
        print("response:")
        print(response_data)
    if response.status_code == 201:
        task_id = response_data.get("uuid")
        print(f"🎯 生成任务已创建，任务ID: {task_id}")
        return task_id
    else:
        print(f"❌ 请求失败，状态码: {response.status_code}")
        print(response.text)
        return None

def load_yaml_tasks(yaml_file):
    with open(yaml_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data

def generate_only_mode(tasks, download_dir, session):
    task_file = os.path.join(download_dir, "task_ids.json")
    new_task_info = {}
    for i, task in enumerate(tasks, 1):
        prompt = task.get('prompt', None)
        try:
            image_paths = resolve_image_paths(task)
        except Exception as e:
            print(f"❌ 任务{task} 解析图片失败: {e}")
            continue
        print(f"\n正在提交第{i}个物体: {image_paths}, prompt: {prompt}")
        task_id = generate_3d_asset_from_images(image_paths, prompt, session)
        if task_id:
            new_task_info[task_id] = {'images': image_paths, 'prompt': prompt}
            print(f"✅ 任务提交成功: {task_id}")
        else:
            print(f"❌ 提交任务失败, images: {image_paths}")
    if new_task_info:
        save_task_info(task_file, new_task_info)
        print(f"\n🎯 本次提交了 {len(new_task_info)} 个任务")
        print(f"📁 任务信息已保存到: {task_file}")
        print("💡 使用 -d 或 --download 选项来下载生成的模型")
    else:
        print("❌ 没有成功提交任何任务")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rodin image-to-3d批量生成工具")
    parser.add_argument(
        "-d", "--download",
        action="store_true",
        help="仅下载模式 - 检查并下载已完成的任务"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="image_to_3d_tasks.yaml",
        help="任务配置yaml文件"
    )
    args = parser.parse_args()

    if not RODIN_API_KEY:
        print("❌ 请设置RODIN_API_KEY环境变量")
        print("例如: export RODIN_API_KEY=your_api_key_here")
        exit(1)

    if not os.path.exists(args.config):
        print(f"❌ 未找到配置文件: {args.config}")
        exit(1)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    tasks = load_yaml_tasks(args.config)
    download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    os.makedirs(download_dir, exist_ok=True)
    session = create_session()
    if args.download:
        print("⬇️  仅下载模式 - 检查并下载已完成的任务")
        download_only_mode(download_dir, session)
    else:
        print("📝 仅生成模式 - 只提交任务，不下载")
        generate_only_mode(tasks, download_dir, session)
