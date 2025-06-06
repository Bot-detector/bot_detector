import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"
