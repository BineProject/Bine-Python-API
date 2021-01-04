from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from .database import BineBaseSQLHandler


class BineContextEditor:
    lot_id: int = -1

    def __init__(self, db_handler: BineBaseSQLHandler) -> None:
        self.db_handler = db_handler
        self._last_block_number: int = 0

    def create_item(self, owner: str, amount: int, item_id: int) -> None:
        self.transfer_item(owner, amount, 0x0, item_id)

    def remove_item(self, owner: str, amount: int, item_id: int) -> None:
        self.transfer_item(0x0, amount, owner, item_id)

    def transfer_item(
        self, to: str, amount: int, transfer_from: str, item_id: int
    ) -> None:
        _from: str = transfer_from
        _id: int = item_id

        if int(_from, base=16) != 0x0:
            self.db_handler.items.remove(_id, _from, amount)
        if int(to, base=16) != 0x0:
            self.db_handler.items.add(_id, to, amount)

    def place_lot(self, owner: str, item_id: int, price: int, amount: int) -> int:
        self.lot_id += 1
        self.db_handler.market.add_lot_data(self.lot_id, owner, item_id, price, amount)
        return self.lot_id

    def buy_lot(self, lot_id: int, buyer: str, amount: int) -> None:
        self.db_handler.market.add_lot_bought_data(lot_id, buyer, amount)

    def cancel_lot(self, lot_id: int) -> None:
        self.db_handler.market.add_lot_canceled(lot_id)
