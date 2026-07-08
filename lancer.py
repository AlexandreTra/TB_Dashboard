"""
Point d'entrée unique — double-cliquez sur ce fichier pour lancer le dashboard.
"""
import os
import sys
import time
import subprocess
import webbrowser

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    app  = os.path.join(here, "Accueil.py")
    env  = os.environ.copy()
    env["STREAMLIT_RUN"] = "1"
    proc = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", app,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "dark",
    ], env=env)
    time.sleep(4)
    webbrowser.open("http://localhost:8501")
    proc.wait()
