
import webbrowser
import time
import threading
from app import app

def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:5000/")

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    print("NOTICE BOARD ORGANIZER IS RUNNING!")
    print("Opening dashboard in your browser...")
    app.run(debug=False)
