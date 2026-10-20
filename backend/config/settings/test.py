from .base import *

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1", "api"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
