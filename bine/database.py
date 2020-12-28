from __future__ import annotations

import typing

import mysql.connector


class ConnectionData(typing.TypedDict):
    host: str
    user: str
    password: str
    database: str


class SQLBasedHandler:
    connection_data: typing.Optional[ConnectionData] = None

    def __init__(self, schema: str = "bine") -> None:
        self._schema = schema

    def init_db(self) -> None:
        with self.con.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {self._schema}")
            cur.execute(f"USE {self._schema}")

            cur.execute(
                "CREATE TABLE IF NOT EXISTS MetaData("
                " name VARCHAR(100) NOT NULL, "
                " lastBlock BIGINT DEFAULT 0, "
                " PRIMARY KEY(name)"
                ")"
            )

            for name, type_hint in typing.get_type_hints(self.__class__).items():
                try:
                    if issubclass(type_hint, SQLBasedFeature):
                        self.__add_feature(name, type_hint)
                except TypeError:
                    pass

        self.commit()

    @classmethod
    def _create_db_connection(cls) -> mysql.connector.MySQLConnection:
        if cls.connection_data is not None:
            return mysql.connector.connect(**cls.connection_data)
        raise NotImplementedError

    @property
    def con(self) -> mysql.connector.MySQLConnection:
        return self._create_db_connection()

    def __add_feature(
        self, name: str, decorator_type: typing.Type[SQLBasedFeature]
    ) -> None:
        decorator = decorator_type(self)
        setattr(self, name, decorator)
        decorator.__post_init__()

    def commit(self) -> None:
        self.con.commit()

    def set_last_block(self, monitor_name: str, block_num: int) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "INSERT INTO MetaData VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE lastBlock = %s",
                (monitor_name, block_num, block_num),
            )

    def get_last_block(self, monitor_name: str) -> int:
        with self.con.cursor() as cur:
            cur.execute(
                "SELECT lastBlock from MetaData WHERE name = %s", (monitor_name,)
            )
            res = cur.fetchone()

            if res is None:
                return 0
            else:
                return res[0]


class SQLBasedFeature:
    def __init__(self, handler: SQLBasedHandler) -> None:
        self.handler = handler

    @property
    def con(self):
        return self.handler.con

    def commit(self) -> None:
        self.handler.commit()

    def __post_init__(self) -> None:
        ...


class BineItemFeature(SQLBasedFeature):
    ItemTableRow = typing.Tuple[str, int]

    def __post_init__(self) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS ItemData( "
                " `address` VARCHAR(50) NOT NULL, "
                " `item` VARCHAR(80) NOT NULL, "
                " `amount` INT NOT NULL, "
                " PRIMARY KEY (`address`, `item`) "
                ")"
            )
        self.commit()

    def add(self, item_id: int, user: str, volume: int) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "INSERT INTO ItemData"
                " VALUES(%s, %s, %s)"
                " ON DUPLICATE KEY"
                " UPDATE `amount` = %s",
                (user, hex(item_id), volume, volume + self.get_amount(item_id, user)),
            )

    def remove(self, item_id: int, user: str, volume: int) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "UPDATE ItemData"
                " SET `amount` = %s"
                " WHERE `address` = %s and `item` = %s",
                (volume - self.get_amount(item_id, user), user, hex(item_id)),
            )

    def get_amount(self, item_id: int, user: str) -> int:
        with self.con.cursor() as cur:
            cur.execute(
                "SELECT `amount` FROM ItemData WHERE `address` = %s and `item` = %s",
                (user, hex(item_id)),
            )
            res = cur.fetchone()

        return (res or [0])[0]

    def get_user_data(self, user: str) -> typing.List[ItemTableRow]:
        with self.con.cursor() as cur:
            cur.execute(
                "SELECT `item`, `amount` "
                "FROM ItemData "
                "WHERE `address` = %s AND `amount` > 0",
                (user,),
            )

            res = cur.fetchall()

            return res or []


class BineMarketFeature(SQLBasedFeature):
    def __post_init__(self) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS MarketLots( "
                " `lot_id` BIGINT NOT NULL, "
                " `owner` VARCHAR(50) NOT NULL, "
                " `item_id` VARCHAR(80) NOT NULL, "
                " `price` VARCHAR(80) NOT NULL, "
                " `amount` BIGINT NOT NULL, "
                ' `status` VARCHAR(30) NOT NULL DEFAULT "ACTIVE", '
                " PRIMARY KEY(`lot_id`) "
                ")"
            )

            cur.execute(
                "CREATE TABLE IF NOT EXISTS MarketDeals("
                " `deal_id` BIGINT NOT NULL AUTO_INCREMENT, "
                " `lot_id` BIGINT NOT NULL, "
                " `buyer` VARCHAR(80) NOT NULL, "
                " `amount` VARCHAR(80) NOT NULL, "
                " PRIMARY KEY (`deal_id`), "
                " FOREIGN KEY (`lot_id`) "
                "  REFERENCES MarketLots(`lot_id`)"
                ")"
            )

    def add_lot_data(
        self, lot_id: int, owner: str, item_id: int, price: int, amount: int
    ) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "INSERT INTO "
                " MarketLots(`lot_id`, `owner`, `item_id`, `price`, `amount`) "
                "VALUES(%s, %s, %s, %s, %s)",
                (lot_id, owner, hex(item_id), price, amount),
            )

    def add_lot_bought_data(self, lot_id: int, buyer: str, amount: int) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "INSERT INTO MarketDeals(`lot_id`, `buyer`, `amount`)"
                "VALUES(%s, %s, %s)",
                (lot_id, buyer, amount),
            )
            cur.execute(
                "UPDATE MarketLots "
                "SET amount = amount - %s,"
                ' status = IF(amount - %s > 0, "PARTIALLY_FILLED", "FILLED")'
                "WHERE lot_id = %s",
                (amount, amount, lot_id),
            )

    def add_lot_canceled(self, lot_id: int) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                "UPDATE MarketLots "
                "SET amount = 0, status = 'CANCELED' "
                "WHERE lot_id = %s",
                (lot_id,),
            )

    def get_items(self) -> typing.List[typing.Tuple[str, int]]:
        with self.con.cursor() as cur:
            cur.execute(
                "SELECT item_id, MIN(price) Min FROM MarketLots GROUP BY item_id"
            )
            return [row for row in cur.fetchall()]

    def get_item_lots(
        self, item_id: int
    ) -> typing.List[typing.Tuple[int, str, str, int]]:
        with self.con.cursor() as cur:
            cur.execute(
                "SELECT lot_id, owner, price, amount"
                " FROM MarketLots"
                " WHERE item_id = %s"
                " AND status IN ('ACTIVE', 'PARTIALLY_FILLED')",
                (hex(item_id),),
            )
            return [row for row in cur.fetchall()]


class BineBaseSQLHandler(SQLBasedHandler):
    items: BineItemFeature
    market: BineMarketFeature


try:
    import flask
    from flask import current_app
except ModuleNotFoundError:

    class FlaskBasedSQLHandler(SQLBasedHandler):
        def __new__(cls) -> FlaskBasedSQLHandler:
            raise ModuleNotFoundError("No installed Flask found.")

        @classmethod
        def _create_db_connection(cls) -> mysql.connector.MySQLConnection:
            raise ModuleNotFoundError("No installed Flask found.")

    class FlaskBineBaseSQLHandler(FlaskBasedSQLHandler, BineBaseSQLHandler):
        def __new__(cls) -> FlaskBineBaseSQLHandler:
            raise ModuleNotFoundError("No installed Flask found.")

        @classmethod
        def _create_db_connection(cls) -> mysql.connector.MySQLConnection:
            raise ModuleNotFoundError("No installed Flask found.")


else:

    class FlaskBasedSQLHandler(SQLBasedHandler):  # type: ignore
        @classmethod
        def _create_db_connection(cls) -> mysql.connector.MySQLConnection:
            return mysql.connector.connect(
                host=current_app.config["MYSQL_DATABASE_HOST"],
                user=current_app.config["MYSQL_DATABASE_USER"],
                password=current_app.config["MYSQL_DATABASE_PASSWORD"],
                database=current_app.config["MYSQL_DATABASE_DB"],
            )

        @property
        def con(self) -> mysql.connector.MySQLConnection:
            if not hasattr(flask.g, "db"):
                flask.g.db = self._create_db_connection()
            return flask.g.db

    class FlaskBineBaseSQLHandler(FlaskBasedSQLHandler, BineBaseSQLHandler):  # type: ignore
        ...