from abc import ABC, abstractmethod
from app.models import BuscaImovelInput


class BaseScraper(ABC):
    nome_fonte: str = "BASE"

    @abstractmethod
    async def buscar(self, params: BuscaImovelInput) -> list[dict]:
        """Retorna lista de dicionários brutos extraídos do portal."""
        raise NotImplementedError
