# Whisper Models

Whisper model binaries are intentionally excluded from Git because they are large.
Joy Flow downloads the selected model automatically on first use.

To download the default model manually:

```powershell
python -c "import whisper; whisper.load_model('small', download_root='models')"
```
