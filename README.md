
###Python libraries to install 
```
pip install selenium requests pyttsx3
```

###Software Requirements
Python 3.8+

Chrome/Chromium browser

OBS Studio with LocalVocal plugin

Ollama (for local AI)

Virtual Audio Cable (VB-Cable or similar)


###Audio Routing Setup
Discord Input: Set to virtual cable OUTPUT (e.g., "CABLE Output")

Discord Output: Set to virtual cable INPUT (e.g., "CABLE Input")

OBS Audio: Capture your microphone

System Sounds: Route through virtual cable as needed


###Known Limitations
Browser Automation: Requires ChromeDriver and may break with Discord updates

Audio Latency: Virtual audio adds ~100ms delay

Transcription Errors: OBS may mis-transcribe certain words

Model Limitations: Small models may generate nonsense occasionally

Token Security: Storing Discord tokens in plaintext is insecure

###Contributing
While this is primarily a personal project, suggestions are welcome:

Fork the repository

Create a feature branch

Submit a pull request with clear description

###License
This project is for educational purposes only. Use at your own risk.
