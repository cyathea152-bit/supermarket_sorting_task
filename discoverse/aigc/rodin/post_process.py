import os
import json
import tqdm
import shutil
import trimesh
import numpy as np
from pathlib import Path

def process_obj_directory(input_dir: str, output_dir: str):
    """
    处理输入目录中的obj文件，进行旋转和平移，并根据info.json重命名输出
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # 查找obj文件
    obj_files = list(input_path.glob("*.obj"))
    if not obj_files:
        print(f"未在 {input_dir} 中找到任何obj文件")
        return
    
    # 查找info.json文件
    info_file = input_path / "info.json"
    if not info_file.exists():
        print(f"未找到 {info_file}")
        return
    
    # 读取info.json并提取prompt
    with open(info_file, 'r', encoding='utf-8') as f:
        try:
            info_data = json.load(f)
            prompt = info_data.get('prompt', 'unnamed')
            # 转换为小写并用下划线替换空格和连字符
            prompt = prompt.split(' -')[0]
            new_name = prompt.lower().replace(' ', '_').replace('-', '_').replace('.', '_').replace(',', '_')
        except json.JSONDecodeError:
            print("无法解析info.json文件")
            return
    
    # 为每个obj文件创建输出目录
    for obj_file in obj_files:
        # 创建新目录
        output_subdir = output_path / new_name
        output_subdir.mkdir(parents=True, exist_ok=True)
        
        # 加载obj文件
        try:
            mesh = trimesh.load(obj_file, force='mesh')
        except Exception as e:
            continue
        
        # 沿X轴旋转90度 (转换为弧度)
        angle = np.radians(90)
        rotation_matrix = trimesh.transformations.rotation_matrix(
            angle, [1, 0, 0], point=[0, 0, 0]
        )
        mesh.apply_transform(rotation_matrix)
        
        # 找到Z轴最低点并移动XY平面到该点
        z_min = mesh.bounds[0][2]  # 最小Z值
        translation = [0, 0, -z_min]
        mesh.apply_translation(translation)
        
        # 查找mtl和纹理文件
        mtl_files = list(input_path.glob("*.mtl"))
        texture_extensions = ['.png', '.jpg', '.jpeg', '.tga', '.bmp', '.tiff']
        texture_files = []
        for ext in texture_extensions:
            texture_files.extend(input_path.glob(f"*{ext}"))
        
        # 保存处理后的obj文件
        new_obj_path = output_subdir / f"{new_name}.obj"
        
        # 使用trimesh保存obj文件，这将自动处理mtl文件
        obj_export = trimesh.exchange.obj.export_obj(mesh, include_texture=True)
        
        # 确保obj文件包含mtllib引用
        lines = obj_export.split('\n')
        has_mtllib = any(line.startswith('mtllib') for line in lines)
        
        with open(new_obj_path, 'w', encoding='utf-8') as f:
            if not has_mtllib and mtl_files:
                # 在第一行注释后添加mtllib引用
                lines_written = False
                for i, line in enumerate(lines):
                    if line.startswith('#') or line.strip() == '':
                        f.write(line + '\n')
                    else:
                        # 在第一个非注释行之前添加mtllib
                        if not lines_written:
                            f.write('mtllib material.mtl\n')
                            f.write('\n')
                            lines_written = True
                        f.write(line + '\n')
                # 如果文件只有注释行，在最后添加mtllib
                if not lines_written:
                    f.write('mtllib material.mtl\n')
            else:
                f.write(obj_export)
        
        # 复制mtl文件并重命名为material.mtl以匹配obj文件中的引用
        for mtl_file in mtl_files:
            new_mtl_path = output_subdir / "material.mtl"
            shutil.copy2(mtl_file, new_mtl_path)
        
        # 复制纹理文件
        for texture_file in texture_files:
            new_texture_path = output_subdir / texture_file.name
            shutil.copy2(texture_file, new_texture_path)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="处理obj文件目录")
    parser.add_argument("input_dir", help="输入目录路径")
    parser.add_argument("--output", dest="output_dir", required=True, help="输出目录路径")
    parser.add_argument("--batch", action="store_true", help="是否启用批处理模式")
    
    args = parser.parse_args()

    if args.batch:
        # 批处理模式
        # use tqdm to show progress
        for subdir in tqdm.tqdm(os.listdir(args.input_dir), desc="Processing directories", unit="directory"):
            if os.path.isdir(os.path.join(args.input_dir, subdir)):
                process_obj_directory(os.path.join(args.input_dir, subdir), args.output_dir)
    else:
        # 单个文件处理模式
        process_obj_directory(args.input_dir, args.output_dir)