from utils.windows import set_app_user_model_id

# Must be called before any GUI elements or windows are created on Windows
set_app_user_model_id()

from app import main

if __name__ == "__main__":
    main()

