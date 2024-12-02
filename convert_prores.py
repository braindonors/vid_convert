import os
import sys
import subprocess
import json
import time
from tqdm import tqdm

VIDEO_EXTENSIONS = {".mov", ".mp4", ".mkv", ".avi"}

def check_gpu_support():
    """Detect available GPU support."""
    try:
        result = subprocess.run(["ffmpeg", "-hwaccels"], stdout=subprocess.PIPE, text=True)
        hw_accels = result.stdout.lower()
        nvidia_support = "cuda" in hw_accels or "nvenc" in hw_accels
        amd_support = "amf" in hw_accels

        if nvidia_support:
            return "nvidia"
        elif amd_support:
            return "amd"
        else:
            return "none"
    except Exception as e:
        print(f"Error detecting GPU support: {e}")
        return "none"

def get_supported_cameras():
    """Retrieve supported camera models for lens correction."""
    try:
        result = subprocess.run(["ffmpeg", "-filters"], stdout=subprocess.PIPE, text=True)
        filters = result.stdout
        if "lensfun" in filters:
            lensfun_index = filters.find("lensfun")
            models_start = filters.find("models", lensfun_index)
            return filters[models_start:].strip()
        return "Lensfun not supported by your FFmpeg installation."
    except Exception as e:
        print(f"Error retrieving supported cameras: {e}")
        return "Error fetching camera models."

def get_file_info(file_path):
    """Retrieve file metadata using ffprobe."""
    try:
        command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=nb_frames,codec_name,duration", "-of", "json", file_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        metadata = json.loads(result.stdout)

        stream = metadata.get("streams", [])[0]
        nb_frames = int(stream.get("nb_frames", 0))
        duration = float(stream.get("duration", 0.0))
        codec_name = stream.get("codec_name", "Unknown")

        command_audio = [
            "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
            "stream=codec_name", "-of", "json", file_path
        ]
        result_audio = subprocess.run(command_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        audio_stream = json.loads(result_audio.stdout).get("streams", [{}])[0]
        audio_codec = audio_stream.get("codec_name", "Unknown")

        return nb_frames, duration, codec_name, audio_codec
    except Exception as e:
        print(f"Error getting file info for {file_path}: {e}")
        return 0, 0.0, "Unknown", "Unknown"

def convert_to_prores_and_proxy(input_file, gpu_type, force_overwrite=False, generate_proxy=False, scale_proxy=False, fisheye_camera=None):
    """Convert a video file to ProRes 422 HQ and optionally generate proxy footage."""
    nb_frames, duration, video_codec, audio_codec = get_file_info(input_file)
    file_dir = os.path.dirname(input_file)
    file_name = os.path.basename(input_file)
    file_base, file_ext = os.path.splitext(file_name)

    if file_ext.lower() not in VIDEO_EXTENSIONS:
        print(f"Skipping unsupported file: {input_file}")
        return

    prores_output_file = os.path.join(file_dir, f"{file_base}_prores{file_ext}")
    proxy_output_file = os.path.join(file_dir, f"{file_base}_proxy.mp4")

    if os.path.exists(prores_output_file) and not force_overwrite:
        print(f"File exists: {prores_output_file}. Skipping (use -f to overwrite).")
        return

    if generate_proxy and os.path.exists(proxy_output_file) and not force_overwrite:
        print(f"File exists: {proxy_output_file}. Skipping proxy (use -f to overwrite).")
        generate_proxy = False

    command = ["ffmpeg", "-i", input_file]

    if gpu_type == "nvidia":
        command += ["-hwaccel", "cuda"]
    elif gpu_type == "amd":
        command += ["-hwaccel", "dxva2"]

    if fisheye_camera:
        command += ["-vf", f"lensfun=camera_model={fisheye_camera}"]

    command += [
        "-c:v", "prores_ks",
        "-profile:v", "prores_hq",
        "-pix_fmt", "yuv422p",
        "-c:a", "copy",
        prores_output_file
    ]

    if generate_proxy:
        proxy_command = [
            "-c:v", "libx265", "-crf", "28", "-preset", "medium", "-c:a", "aac"
        ]
        if scale_proxy:
            proxy_command += ["-vf", "scale=iw*0.5:ih*0.5"]
        proxy_command.append(proxy_output_file)
        command += proxy_command

    print(f"Processing: {file_name}")
    with tqdm(total=nb_frames, desc="Progress", unit="frame") as pbar:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        start_time = time.time()
        for line in process.stdout:
            if "frame=" in line:
                try:
                    frame = int(line.split("frame=")[1].split()[0])
                    elapsed_time = time.time() - start_time
                    eta = (elapsed_time / frame) * (nb_frames - frame) if frame > 0 else 0
                    pbar.n = frame
                    pbar.set_postfix({"Elapsed": f"{elapsed_time:.2f}s", "ETA": f"{eta:.2f}s", "Percent": f"{(frame / nb_frames) * 100:.2f}%"})
                    pbar.update(0)
                except (IndexError, ValueError):
                    continue

        process.wait()
        pbar.close()

def process_directory(directory, gpu_type, force_overwrite=False, generate_proxy=False, scale_proxy=False, fisheye_camera=None):
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.", file=sys.stderr)
        return

    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            convert_to_prores_and_proxy(file_path, gpu_type, force_overwrite, generate_proxy, scale_proxy, fisheye_camera)

def main():
    if "--help" in sys.argv:
        print("Usage: python convert_to_prores.py [-f] [--proxy] [--scale] [--fisheye CAMERA_MODEL] <directory1> [directory2 ...]")
        print("\nSupported camera models:")
        print(get_supported_cameras())
        sys.exit(0)

    force_overwrite = False
    generate_proxy = False
    scale_proxy = False
    fisheye_camera = None
    directories = []

    for arg in sys.argv[1:]:
        if arg == "-f":
            force_overwrite = True
        elif arg == "--proxy":
            generate_proxy = True
        elif arg == "--scale":
            scale_proxy = True
        elif arg.startswith("--fisheye"):
            fisheye_camera = arg.split("=")[1] if "=" in arg else None
        else:
            directories.append(arg)

    gpu_type = check_gpu_support()
    print(f"Detected GPU: {gpu_type}")

    for directory in directories:
        process_directory(directory, gpu_type, force_overwrite, generate_proxy, scale_proxy, fisheye_camera)

if __name__ == "__main__":
    main()
