import subprocess
import os

if __name__ == "__main__":
    os.environ["STREAMLIT_EMAIL_ADDRESS"] = ""
    os.environ["STREAMLIT_DISABLE_EMAIL_COLLECTION"] = "true"

    os.environ["STREAMLIT_SERVER_PORT"] = "8181"
    os.environ["STREAMLIT_SERVER_ADDRESS"] = "0.0.0.0"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_SERVER_ADDRESS"] = "localhost"
    os.environ["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
    os.environ["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "false"
    os.environ["STREAMLIT_GLOBAL_SHOW_DEPLOY_BUTTON"] = "false"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    os.environ["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    os.environ["STREAMLIT_CLIENT_TOOLBAR_MODE"] = "minimal"
    os.environ["STREAMLIT_CLIENT_SHOW_SIDEBAR_NAVIGATION"] = "false"
    os.environ["STREAMLIT_CLIENT_SHOW_ERROR_DETAILS"] = "false"

    script_path = os.path.abspath("app.py")
    subprocess.run(["streamlit", "run", script_path])
