# Joy Flow

Joy Flow is a Windows accessibility and productivity application by **LazyRichie**. It turns a compatible game controller into a mouse and navigation tool, with configurable controls, voice dictation powered by OpenAI Whisper, an on-screen overlay, system-tray controls, and multilingual light/dark interfaces.

## Features

- Controller-driven cursor movement and clicking
- Configurable mappings and behavior
- Hold-to-talk Whisper voice dictation
- English and Simplified Chinese interfaces
- Light and dark themes
- On-screen controller overlay
- System-tray controls and single-instance protection
- Persistent local configuration
- Standalone Windows executable build

## Requirements

- Windows 10 or Windows 11
- Python 3.12 recommended
- A compatible game controller
- A microphone for voice dictation

## Install and Run

```powershell
git clone https://github.com/richarddong124-boop/Joy_Flow.git
cd Joy_Flow
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python controller_desktop_tray.py
```

The first use of voice dictation may download the selected Whisper model into the `models` folder. The default model is `small`, and the model can be changed from the application settings.

## Build the Windows Executable

With the virtual environment activated:

```powershell
pip install pyinstaller
pyinstaller --clean --noconfirm ControllerMouseOneFile.spec
```

The resulting application will be available at:

```text
dist/Joy Flow.exe
```

If Whisper model files are present in `models/` at build time, the PyInstaller specification bundles them into the executable. Model binaries are intentionally excluded from this repository because of their size.

## Whisper Models

Joy Flow uses the `openai-whisper` Python package. Whisper model files (`*.pt`) are downloaded automatically when needed and are not committed to Git.

To prepare a model manually, run Python after installing the requirements:

```powershell
python -c "import whisper; whisper.load_model('small', download_root='models')"
```

You can replace `small` with another supported Whisper model name such as `tiny`.

## Project Structure

```text
Joy_Flow/
??? models/                       Local Whisper models (not committed)
??? pyinstaller_hooks/            Custom PyInstaller hook for Torch
??? app_paths.py                  Runtime and application-data paths
??? controller_bridge.py          Interface-to-backend bridge
??? controller_desktop_tray.py    Desktop and system-tray entry point
??? controller_mouse_app.py       Core controller and mouse logic
??? controller_mouse_config.json  Default application configuration
??? controller_mouse_logo.ico     Windows application icon
??? controller_overlay.js         On-screen overlay logic
??? controller_ui.html            Main interface
??? controlleruisub*.html         Theme and language variants
??? voice_dictation.py            Whisper dictation support
??? win32_mouse.py                Windows mouse integration
??? ControllerMouseOneFile.spec   Single-file PyInstaller build
??? joy_flow_version_info.txt     Windows version metadata
??? requirements.txt              Python dependencies
```

## Reporting Issues

Please use [GitHub Issues](https://github.com/richarddong124-boop/Joy_Flow/issues) and include:

- Windows version
- Controller model
- Joy Flow version
- Steps to reproduce
- Relevant error messages or logs

Do not include passwords, access tokens, or other sensitive information.

## Contributing

Contributions are welcome. Fork the repository, create a focused branch, and submit a pull request describing the change and how it was tested.

## License

Joy Flow is released under the [MIT License](LICENSE).

Copyright (c) 2026 LazyRichie.
