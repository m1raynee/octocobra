import os
import sys

class Config:
    def __init__(self):
        if '.env' in os.listdir():
            from dotenv import load_dotenv
            load_dotenv()
            del load_dotenv
    def __getattribute__(self, name: str):
        return os.environ.get(name)

sys.modules[__name__] = Config()

# typings
TOKEN: str