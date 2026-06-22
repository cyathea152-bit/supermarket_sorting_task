from .airbot_task_base import AirbotPlayTaskBase, recoder_airbot_play
from .mmk2_task_base import MMK2TaskBase, recoder_mmk2

import os
import shutil
import pickle
import mediapy
from concurrent.futures import ThreadPoolExecutor

def copypy2(source_py, target_py):
    shutil.copy2(source_py, target_py)

    with open(target_py, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    in_main_block = False
    for line in lines:
        if in_main_block:
            break
        elif line.strip().startswith('if __name__'):
            in_main_block = True
            continue
        else:
            new_lines.append(line)

    mjcf_index = None
    for i, line in enumerate(new_lines):
        if line.strip().startswith('cfg.mjcf_file_path'):
            mjcf_index = i
            break

    if mjcf_index is not None:
        new_mjcf_path = 'os.path.abspath(__file__).replace(".py", ".mjb")'
        new_lines[mjcf_index] = f'cfg.mjcf_file_path = {new_mjcf_path}\n'

    with open(target_py, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

def encode_single_video(task):
    """编码单个视频文件"""
    try:
        data_path = task['data_path']
        output_path = task['output_path']
        fps = task['fps']
        
        # 加载视频帧数据
        with open(data_path, 'rb') as f:
            frames = pickle.load(f)
        
        # 编码视频
        mediapy.write_video(output_path, frames, fps=fps)
        
        # 删除临时数据文件
        os.remove(data_path)
        
        return True, output_path
    except Exception as e:
        return False, str(e)

def batch_encode_videos(video_tasks, max_workers=4):
    """批量编码视频，限制并发数量"""
    if not video_tasks:
        return
        
    print(f"开始批量编码 {len(video_tasks)} 个视频，最大并发数: {max_workers}")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(encode_single_video, task) for task in video_tasks]
        
        success_count = 0
        for i, future in enumerate(futures):
            try:
                success, result = future.result()
                if success:
                    success_count += 1
                    print(f"\r编码进度: {success_count}/{len(video_tasks)}", end="", flush=True)
                else:
                    print(f"\n视频编码失败: {result}")
            except Exception as e:
                print(f"\n视频编码异常: {e}")
    
    print(f"\n批量编码完成，成功: {success_count}/{len(video_tasks)}")