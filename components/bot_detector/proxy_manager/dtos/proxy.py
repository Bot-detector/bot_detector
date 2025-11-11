from pydantic import BaseModel


class Ports(BaseModel):
    http: int
    socks5: int


class Proxy(BaseModel):
    username: str
    password: str
    proxy_address: str
    ports: Ports

    @property
    def url(self) -> str:
        return (
            f"http://{self.username}:{self.password}"
            f"@{self.proxy_address}:{self.ports.http}"
        )
