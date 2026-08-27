import yt_dlp
import os

def download_audio_from_url(url: str, output_folder: str = "downloads") -> str:
    """
    Downloads audio from a given URL (e.g., YouTube) and returns the path to the audio file.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_folder}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            # The postprocessor changes the extension to mp3
            filename = ydl.prepare_filename(info_dict)
            base, _ = os.path.splitext(filename)
            mp3_filename = base + '.mp3'
            return mp3_filename
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None
