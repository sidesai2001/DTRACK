# DMTS - Data Management & Tracking System (Fixed + Mobile Responsive)

This version fixes `UnboundLocalError: pd`, improves error handling, and adds mobile-friendly UI.
It includes a mock scanner so you can test without hardware . Optional webcam scanning is auto-detected
if you install `streamlit-webcam-qrcode-scanner`.

## Run
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Default admin:
- user: admin
- pass: admin123
