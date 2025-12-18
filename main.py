import sys
import os

# Ensure the root directory is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gui.app import SolarApp

if __name__ == "__main__":
    app = SolarApp()
    app.mainloop()