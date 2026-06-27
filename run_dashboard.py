"""Lance le dashboard web.  Utilisation :  python run_dashboard.py"""
from bot.config import DASHBOARD_PORT
from dashboard.app import create_app

if __name__ == "__main__":
    app = create_app()
    print(f"Dashboard demarre sur http://localhost:{DASHBOARD_PORT}")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
