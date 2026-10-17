from abc import ABC, abstractmethod


class MusicProvider(ABC):
    """Shared contract for music catalog providers."""

    @abstractmethod
    def search(self, query, **kwargs):
        """Search for tracks using this provider."""
        raise NotImplementedError

    def get_restrictions(self, resource_id, **kwargs):
        """Fetch region or availability metadata for a resource."""
        raise NotImplementedError
