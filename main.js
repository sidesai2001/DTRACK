const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let streamlitProcess = null;
let mainWindow = null;

// Disable GPU acceleration to fix rendering issues
app.disableHardwareAcceleration();

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false,
      allowRunningInsecureContent: true,
    },
  });

  // Open DevTools for debugging
  mainWindow.webContents.openDevTools();

  // Add headers for WebSocket
  mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': ['default-src * \'unsafe-inline\' \'unsafe-eval\'; script-src * \'unsafe-inline\' \'unsafe-eval\'; connect-src * \'unsafe-inline\'; img-src * data: blob: \'unsafe-inline\'; frame-src *; style-src * \'unsafe-inline\';']
      }
    });
  });

  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    console.error('Failed to load:', errorCode, errorDescription);
  });

  mainWindow.webContents.on('did-finish-load', () => {
    console.log('Page loaded successfully');
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function waitForStreamlit() {
  const http = require('http');
  let attempts = 0;
  const maxAttempts = 60;
  
  const checkServer = () => {
    attempts++;
    console.log(`Checking Streamlit... Attempt ${attempts}`);
    
    http.get('http://localhost:8501', (res) => {
      console.log(`Streamlit responded with status: ${res.statusCode}`);
      if (res.statusCode === 200) {
        console.log('Loading Streamlit in Electron window...');
        
        // Wait a bit more for Streamlit to be fully ready
        setTimeout(() => {
          mainWindow.loadURL('http://localhost:8501', {
            userAgent: 'Chrome'
          });
          mainWindow.show();
        }, 1000);
      } else {
        setTimeout(checkServer, 500);
      }
    }).on('error', (err) => {
      console.log(`Connection error: ${err.message}`);
      if (attempts < maxAttempts) {
        setTimeout(checkServer, 500);
      } else {
        console.error('Failed to connect to Streamlit after 30 seconds');
      }
    });
  };
  setTimeout(checkServer, 2000);
}

function startStreamlit() {
  const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
  
  streamlitProcess = spawn(pythonPath, [
    '-m', 'streamlit', 'run',
    path.join(__dirname, 'streamlit-app', 'app.py'),
    '--server.headless=true',
    '--server.port=8501',
    '--browser.serverAddress=localhost',
    '--browser.gatherUsageStats=false'
  ]);

  streamlitProcess.stdout.on('data', (data) => {
    console.log(`Streamlit STDOUT: ${data}`);
  });

  streamlitProcess.stderr.on('data', (data) => {
    console.log(`Streamlit STDERR: ${data}`);
  });

  streamlitProcess.on('error', (error) => {
    console.error(`Failed to start Streamlit: ${error}`);
  });
}

app.on('ready', () => {
  startStreamlit();
  createWindow();
  waitForStreamlit();
});

app.on('window-all-closed', () => {
  if (streamlitProcess) {
    streamlitProcess.kill();
  }
  app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});