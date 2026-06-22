import os
import json
import requests

RODIN_API_KEY = os.getenv("RODIN_API_KEY")

API_ENDPOINT = "https://api.hyper3d.com/api/v2/rodin"


def create_session():
    """创建HTTP session"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    return session


def load_task_info(task_file):
    """读取任务信息文件"""
    if os.path.exists(task_file):
        try:
            with open(task_file, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取任务文件失败: {e}")
            return {}
    return {}


def save_task_info(task_file, task_info):
    """增量保存任务信息"""
    existing_tasks = load_task_info(task_file)
    existing_tasks.update(task_info)
    with open(task_file, "w", encoding='utf-8') as f:
        json.dump(existing_tasks, f, ensure_ascii=False, indent=2)

def remove_completed_task(task_file, task_id):
    """删除已完成的任务"""
    existing_tasks = load_task_info(task_file)
    if task_id in existing_tasks:
        del existing_tasks[task_id]
        with open(task_file, "w", encoding='utf-8') as f:
            json.dump(existing_tasks, f, ensure_ascii=False, indent=2)
        print(f"已从任务列表中移除: {task_id}")


def check_task_status(task_id, session=None):
    if session is None:
        session = create_session()
    ENDPOINT = "https://api.hyper3d.com/api/v2/download"
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {RODIN_API_KEY}',
    }
    data = {
        "task_uuid": task_id
    }
    response = session.post(
        ENDPOINT,
        headers=headers,
        json=data,
        timeout=(10, 60)
    )
    if response.status_code == 201 and response.json().get("list"):
        file_list = response.json().get("list")
        download_files = {}
        file_names = []
        for file in file_list:
            file_name = file.get('name')
            file_names.append(file_name)
            download_files[file_name] = file.get('url')
        print(f"检测到文件: {', '.join(file_names)}")
        if len(file_names) > 1:
            return download_files
        else:
            print("⏳ 仅有预览文件，等待3D模型生成...")
    return None


def download_only_mode(download_dir, session):
    """仅下载模式：读取任务文件并下载完成的任务"""
    task_file = os.path.join(download_dir, "task_ids.json")
    task_info = load_task_info(task_file)
    
    if not task_info:
        print("📭 没有找到待下载的任务")
        print(f"请检查文件: {task_file}")
        return
    
    task_ids = list(task_info.keys())
    print(f"📋 找到 {len(task_ids)} 个待下载的任务")
    
    completed_tasks = []
    for task_id in task_ids:
        print(f"\n📋 检查任务状态: {task_id}")
        download_files = check_task_status(task_id, session)
        if download_files:
            print(f"🎉 任务完成，开始下载 {len(download_files)} 个文件...")
            os.makedirs(os.path.join(download_dir, task_id), exist_ok=True)
            
            # 获取任务对应的prompt
            current_prompt = task_info.get(task_id, "未知prompt")
            with open(os.path.join(download_dir, task_id, "info.json"), "w", encoding='utf-8') as f:
                json.dump({
                    "prompt": current_prompt,
                    "task_id": task_id,
                    "download_files": download_files
                }, f, ensure_ascii=False, indent=2)
                
            # 下载所有文件
            for file_name, download_url in download_files.items():
                print(f"⬇️  正在下载: {file_name}")
                response = session.get(download_url, timeout=(10, 120))
                with open(os.path.join(download_dir, task_id, file_name), "wb") as f:
                    f.write(response.content)
                print(f"✅ 下载完成: {file_name}")
            
            # 生成base.mtl文件
            mtl_content = """newmtl material_0\nmap_Kd texture_diffuse.png\nmap_Ns texture_roughness.png\nmap_Bump texture_normal.png\nmap_Pm texture_metallic.png\nmap_Pr texture_pbr.png"""
            mtl_file_path = os.path.join(download_dir, task_id, "base.mtl")
            with open(mtl_file_path, "w", encoding='utf-8') as f:
                f.write(mtl_content)
            print(f"✅ 生成材质文件: base.mtl")
            
            completed_tasks.append(task_id)
            print(f"🎊 任务 {task_id} 下载完成！")
        else:
            print(f"⏳ 任务 {task_id} 仍在生成中...")
    
    # 删除已完成的任务
    for task_id in completed_tasks:
        remove_completed_task(task_file, task_id)
    
    if completed_tasks:
        print(f"\n✅ 完成下载 {len(completed_tasks)} 个任务")
    
    remaining_tasks = len(task_ids) - len(completed_tasks)
    if remaining_tasks > 0:
        print(f"⏳ 还有 {remaining_tasks} 个任务仍在生成中，请稍后再次运行下载")
