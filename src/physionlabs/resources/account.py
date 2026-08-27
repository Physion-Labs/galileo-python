"""Who you are, what you may run, what it costs, and whether we are up."""

from __future__ import annotations

from .._transport import Transport
from ..models import Account as AccountModel
from ..models import Credits, ModelList, QuotaReport, SystemStatus


class Account:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def retrieve(self) -> AccountModel:
        """Your account.

        Also the cheapest way to check that a key works: no video, no credits, and
        an ``AuthenticationError`` if the key is wrong.
        """
        return AccountModel.model_validate(self._t.json(method="GET", path="/v1/me"))

    def models(self) -> ModelList:
        return ModelList.model_validate(self._t.json(method="GET", path="/v1/models"))

    def quota(self) -> QuotaReport:
        return QuotaReport.model_validate(self._t.json(method="GET", path="/v1/quota"))

    def credits(self) -> Credits:
        return Credits.model_validate(self._t.json(method="GET", path="/v1/credits"))

    def status(self) -> SystemStatus:
        """Platform health.

        The one endpoint that needs no key, so it still answers when the problem
        is your credentials.
        """
        return SystemStatus.model_validate(
            self._t.json(method="GET", path="/v1/status", anonymous=True)
        )
