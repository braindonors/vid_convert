import os
import sys
import subprocess
import json
import time
from tqdm import tqdm  # For the progress bar

# Supported video file extensions
VIDEO_EXTENSIONS = {".mov", ".mp4", ".mkv", ".avi"}

def get_file_info(file_path):
    """Retrieve file metadata using ffprobe."""
    try:
        # Run ffprobe to get file metadata in JSON format
        command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=nb_frames,codec_name,duration", "-of", "json", file_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        metadata = json.loads(result.stdout)

        # Extract relevant metadata
        stream = metadata.get("streams", [])[0]
        nb_frames = int(stream.get("nb_frames", 0))
        duration = float(stream.get("duration", 0.0))
        codec_name = stream.get("codec_name", "Unknown")

        # Extract audio codec
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

def convert_to_prores(input_file):
    """Convert a video file to ProRes 422 HQ with a progress bar."""
    # Get metadata
    nb_frames, duration, video_codec, audio_codec = get_file_info(input_file)

    # Get the file's directory, base name, and extension
    file_dir = os.path.dirname(input_file)
    file_name = os.path.basename(input_file)
    file_base, file_ext = os.path.splitext(file_name)

    # Skip files without a valid extension
    if file_ext.lower() not in VIDEO_EXTENSIONS:
        print(f"Skipping unsupported file: {input_file}")
        return

    # Construct the output file path
    output_file = os.path.join(file_dir, f"{file_base}_prores{file_ext}")

    # Build the ffmpeg command
    command = [
        "ffmpeg",
        "-i", input_file,
        "-c:v", "prores_ks",
        "-profile:v", "prores_hq",
        "-pix_fmt", "yuv422p",
        "-c:a", "copy",
        output_file
    ]

    # Display metadata and start progress
    print(f"\nProcessing: {file_name}")
    print(f"Codec: {video_codec} (Audio: {audio_codec}) ... converting to ProRes 422 HQ")
    print(f"Duration: {duration:.2f}s ({nb_frames} frames)\n")

    with tqdm(total=nb_frames, desc="Progress", unit="frame") as pbar:
        # Run the ffmpeg command and capture output
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        start_time = time.time()
        for line in process.stdout:
            if "frame=" in line:
                # Extract frame number from the output
                try:
                    frame = int(line.split("frame=")[1].split()[0])
                    elapsed_time = time.time() - start_time
                    eta = (elapsed_time / frame) * (nb_frames - frame) if frame > 0 else 0
                    pbar.n = frame
                    pbar.set_postfix({
                        "Elapsed": f"{elapsed_time:.2f}s",
                        "ETA": f"{eta:.2f}s",
                        "Percent": f"{(frame / nb_frames) * 100:.2f}%"
                    })
                    pbar.update(0)  # Refresh bar
                except (IndexError, ValueError):
                    continue

        process.wait()
        pbar.close()

        if process.returncode == 0:
            print(f"Successfully processed: {output_file}")
        else:
            print(f"Error processing: {input_file}", file=sys.stderr)

def process_directory(directory):
    """Process all video files in a directory and its subdirectories."""
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.", file=sys.stderr)
        return

    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            convert_to_prores(file_path)

def main():
    """Main function to handle user input and process directories."""
    if len(sys.argv) < 2:
        print("Usage: python convert_to_prores.py <directory1> [directory2 ...]")
        sys.exit(1)

    directories = sys.argv[1:]
    for directory in directories:
        print(f"Processing directory: {directory}")
        process_directory(directory)

if __name__ == "__main__":
    main()
