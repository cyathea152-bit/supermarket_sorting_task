import os
import sys
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

def generate_3d_asset(prompt, session=None):
    if session is None:
        session = create_session()
        
    headers = {
        "Authorization": f"Bearer {RODIN_API_KEY}",
    }
    
    # 使用multipart/form-data格式
    files = {
        'prompt': (None, prompt),
        'geometry_file_format': (None, 'obj'),
        'quality': (None, 'medium')
    }
    
    response = session.post(
        API_ENDPOINT, 
        headers=headers, 
        files=files,
        timeout=(10, 60)
    )
    
    # 在仅生成模式下减少输出
    response_data = response.json()
    if response.status_code == 201:
        print(f"✅ API调用成功，状态码: {response.status_code}")
    else:
        print("response:")
        print(response_data)
    
    if response.status_code == 201:
        task_id = response_data.get("uuid")  # 正确的字段名是uuid
        print(f"🎯 生成任务已创建，任务ID: {task_id}")
        return task_id
    else:
        print(f"❌ 请求失败，状态码: {response.status_code}")
        print(response.text)
        return None

def generate_only_mode(prompts, download_dir, session):
    """仅生成模式：只提交任务，不下载"""
    task_file = os.path.join(download_dir, "task_ids.json")
    
    new_task_info = {}
    for i, prompt in enumerate(prompts, 1):
        print(f"\n正在提交第{i}个物体: {prompt}")
        task_id = generate_3d_asset(prompt, session)
        if task_id:
            new_task_info[task_id] = prompt
            print(f"✅ 任务提交成功: {task_id}")
        else:
            print(f"❌ 提交任务失败, prompt: {prompt[:20]}...")

    if new_task_info:
        save_task_info(task_file, new_task_info)
        print(f"\n🎯 本次提交了 {len(new_task_info)} 个任务")
        print(f"📁 任务信息已保存到: {task_file}")
        print("💡 使用 -d 或 --download 选项来下载生成的模型")
    else:
        print("❌ 没有成功提交任何任务")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rodin 3D模型生成工具")
    parser.add_argument(
        "-d", "--download",
        action="store_true",
        help="仅下载模式 - 检查并下载已完成的任务"
    )
    args = parser.parse_args()
    if not RODIN_API_KEY:
        print("❌ 请设置RODIN_API_KEY环境变量")
        print("例如: export RODIN_API_KEY=your_api_key_here")
        exit(1)
    download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    os.makedirs(download_dir, exist_ok=True)
    session = create_session()
    if args.download:
        print("⬇️  仅下载模式 - 检查并下载已完成的任务")
        download_only_mode(download_dir, session)
    else:
        if os.path.exists("prompt.txt"):
            with open("prompt.txt", "r", encoding='utf-8') as f:
                prompts = f.readlines()
                prompts = [prompt.strip() for prompt in prompts if prompt.strip()]
        else:
            prompts = [
                "生成一个模型玩具车。高度细节化的科幻装甲战车模型，流线型钛合金车身带有发光能量槽，六轮全地形悬浮底盘，车顶配备可旋转等离子炮台，车体有仿生机械纹理和全息投影仪表盘，整体采用赛博朋克风格的霓虹蓝紫配色，表面有纳米涂层反光效果，背景是火星荒漠场景"
            ]
        print("📝 仅生成模式 - 只提交任务，不下载")
        generate_only_mode(prompts, download_dir, session)
