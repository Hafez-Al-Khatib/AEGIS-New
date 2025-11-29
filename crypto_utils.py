from cryptography.fernet import Fernet
import os

# Generate a key if it doesn't exist, otherwise load it
# In production, this should be stored in a secure vault or env var
KEY_FILE = "d:\\Aegis\\secret.key"

def load_key():
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file:
            key_file.write(key)
        print(f"[CRYPTO] Generated new encryption key at {KEY_FILE}")
    else:
        with open(KEY_FILE, "rb") as key_file:
            key = key_file.read()
    return key

# Singleton Cipher Suite
_cipher_suite = None

def get_cipher_suite():
    global _cipher_suite
    if _cipher_suite is None:
        key = load_key()
        _cipher_suite = Fernet(key)
    return _cipher_suite

def encrypt_content(content: str) -> bytes:
    """Encrypts a string content."""
    cipher = get_cipher_suite()
    return cipher.encrypt(content.encode('utf-8'))

def decrypt_content(encrypted_content: bytes) -> str:
    """Decrypts bytes content back to string."""
    cipher = get_cipher_suite()
    return cipher.decrypt(encrypted_content).decode('utf-8')
