from pydantic import BaseSettings


class Settings(BaseSettings):
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    elevenlabs_api_key: str = ""

    class Config:
        env_file = ".env"
