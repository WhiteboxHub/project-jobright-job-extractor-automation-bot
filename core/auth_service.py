import os
import requests
from core.logger import logger
from config.settings import settings

class AuthService:
    """Service to handle authentication and access token generation"""
    
    def __init__(self):
        self.auth_url = settings.AUTH_URL
        self.username = settings.AUTH_USERNAME
        self.password = settings.AUTH_PASSWORD
        self._access_token = None

    def get_access_token(self, force_refresh=False):
        if self._access_token and not force_refresh:
            return self._access_token

        if not all([self.auth_url, self.username, self.password]):
            logger.error("Authentication credentials missing in .env")
            return None

        try:
            logger.info(f"Requesting access token from: {self.auth_url}")
            payload = {
                "username": self.username,
                "password": self.password
            }
            response = requests.post(self.auth_url, data=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            token = (
                data.get("access_token") or 
                data.get("token") or 
                data.get("data", {}).get("token") or
                data.get("result", {}).get("access_token")
            )
            if token:
                logger.info("Access token generated successfully")
                self._access_token = token
                return token
            else:
                logger.error(f"Token not found in response: {data}")
                return None
        except Exception as e:
            logger.error(f"Authentication request failed: {e}")
            return None

auth_service = AuthService()

class BaseAPIClient:
    def __init__(self):
        base = settings.AUTH_URL.replace('/login', '').replace('/api/login', '')
        if '/api' not in base:
            base += '/api'
        self.base_url = os.getenv("API_BASE_URL", base)
        self.token = os.getenv("API_TOKEN")

    def _get_headers(self):
        headers = {"Content-Type": "application/json"}
        token = self.token or auth_service.get_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def get(self, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        return requests.get(url, headers=self._get_headers(), **kwargs)

    def post(self, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        return requests.post(url, headers=self._get_headers(), **kwargs)
