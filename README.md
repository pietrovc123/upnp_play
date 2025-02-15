upnp_play - Play/Cast an Audio File/Playlist to a UPNP/DLNA Device Renderer

upnp_play is a program written in Python 3 that allows you to play/cast MP3/FLAC audio files from your PC to a TV or any other UPNP-compatible device.
Samsung Smart TVs are already UPNP compatible, while for other TVs, you may need to purchase an Android box and install either Kodi (free) or BubbleUPnP (paid, costs €5.99).

Installation
Download and extract upnp_play zip file into a directory different from where your audio files are stored. The prerequisites for installation are as follows:

    Linux
    Python 3 and its libraries are usually pre-installed, so you only need to run:
    python3 -m venv upnp-play-env
    source upnp-play-env/bin/activate
    pip install -r requirements.txt
    python3 upnp_play.py

    Windows
    Follow these steps:
    1) Download and install the stable release of Python.
    2) Download and install Visual C++ Build Tools and select C++ (requires a lot of space).
    3) Install the necessary libraries using the following commands:
    python -m venv upnp-play-env
    source upnp-play-env/bin/activate
    pip install -r requirements.txt
    python upnp_play.py

You can use "n" and wait a few second to skip the current song, "p" to pause and "c" to continue.

Android Box Configuration
If you are using an Android box, you need to configure and enable media rendering for the apps:

    Kodi: Settings (gear icon) → Services → UPNP/DLNA → Enable "Allow remote control via UPNP"

    BubbleUPnP: More → Settings (gear icon) → Local Renderer → Enable "Allow remote control"

Configuration
Before running upnp_play, you need to edit the configuration file config.ini:


# --- Configuration ---
SERVER_PORT = 8000
directory_path = /mnt/music
threshold = 0
order_files = True  # Set to True to sort files, False to randomize order

Parameter Explanation
SERVER_PORT: The internal web server port (default 8000 is usually fine).

directory_path: The directory containing MP3 or FLAC audio files.

threshold:
    0 → Starts playback from the first file.
    10 → Starts playback from the 10th file onwards (useful if files are numbered sequentially, e.g., 010file, 011file, etc.).

order_files:
    True → Sorts files in order.
    False → Plays files in random order.



DISCLAIMER
upnp_play is provided "as is" without any warranties, express or implied. The user assumes full responsibility for using this software.

    Security & Vulnerability Risks: Running upnp_play may expose your device to potential security vulnerabilities, especially if UPNP/DLNA is enabled on a public network. 
    It is strongly recommended to use it within a secure and private network.

    Device Compatibility: Not all UPNP/DLNA devices may function correctly with upnp_play. Compatibility issues may arise depending on the device model, firmware, or network settings.

    Potential Device Damage: While upnp_play does not modify system files or hardware settings, improper configuration, frequent use, or unexpected software behavior could lead to device malfunctions, overheating, 
    or performance degradation. The developers are not responsible for any damage, data loss, or system failures resulting from the use of this software.

    Third-Party Applications: If using third-party applications like Kodi or BubbleUPnP, ensure they are downloaded from official sources. The developers of upnp_play are not responsible 
    for any security risks or issues arising from third-party software.

By using upnp_play, you acknowledge and accept these risks. If you are unsure about any configuration settings or security concerns, consult an IT professional before proceeding.

