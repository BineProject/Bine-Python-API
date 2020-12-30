from __future__ import annotations

import hashlib
import time
import typing
import collections

import web3
import web3.types


class Event(typing.TypedDict):
    args: typing.Mapping[str, typing.Any]
    event: str
    logIndex: int
    transactionIndex: int
    transactionHash: web3.types.HexBytes
    address: str
    blockHash: web3.types.HexBytes
    blockNumber: int


class IEventFilter(typing.Protocol):
    def get_new_entries(self) -> typing.List[Event]:
        ...

    def get_all_entries(self) -> typing.List[Event]:
        ...


_filter_connections: typing.DefaultDict[
    str, typing.Dict[str, typing.Callable]
] = collections.defaultdict(lambda: {})


def connect_event(cls_name: str, event: str):
    def connect_event_decorator(func: typing.Callable) -> typing.Callable:
        _filter_connections[cls_name][event] = func
        return func

    return connect_event_decorator


def create_event_decorator(cls_name: str):
    return lambda event: connect_event(cls_name, event)


class ContractMonitor:
    @property
    def __filter_connections(self):
        return _filter_connections[self.__class__.__name__]

    def __init__(
        self,
        web3_provider: web3.Web3,
        contract_address: web3.types.Address,
        contract_abi: typing.Any,
        from_block: int = 0,
    ) -> None:
        # Client instance to interact with the blockchain
        self.web3 = web3_provider
        # Set the default account
        # (so we don't need to set the "from" for every transaction call)
        while True:
            try:
                self.web3.eth.defaultAccount = self.web3.eth.accounts[0]  # type: ignore
            except:
                print("Ganache is not running, trying again in 5 seconds")
                time.sleep(5)
            else:
                break
        self.from_block = from_block
        self.deployed_contract_address = contract_address
        contract_abi = contract_abi

        # Fetch deployed contract reference
        self.contract = self.web3.eth.contract(
            address=self.deployed_contract_address, abi=contract_abi
        )

        self._last_block_data: typing.Any = None
        self.last_processed_block = from_block

        # Block number -> event hash -> event data
        self.events: typing.Dict[int, typing.Dict[str, Event]] = {}

    def _create_filter(self, event: str, *args, **kwargs) -> IEventFilter:
        return getattr(self.contract.events, event).createFilter(*args, **kwargs)

    def __on_next_block_added(self, block_data):
        self._last_block_data = block_data
        print(f"New block added: {block_data['number']}")
        self._on_next_block_added(block_data)

    def process_event(self, event: Event, callback: typing.Callable) -> None:
        block_number = event["blockNumber"]
        if block_number > self.last_processed_block:
            self.__on_next_block_added(self.web3.eth.getBlock(block_number))
            self.last_processed_block = block_number

        event_hash = hashlib.sha256(str(event).encode("utf-8")).hexdigest()

        if block_number not in self.events:
            self.events[block_number] = {}
        elif event_hash in self.events[block_number]:
            print(
                f"[{self.__class__.__name__}] " "Duplicate event on block",
                block_number,
                "with hash",
                event_hash,
                " : ",
                event,
            )
            return

        self.events[block_number][event_hash] = event

        args = dict(event["args"])
        callback(self, **args)

    def run_tracker(self) -> None:
        loaded_block = self.from_block
        latest_block = self.web3.eth.getBlock("latest")["number"]

        print("Starting monitoring for a contract", self.deployed_contract_address)

        self.filters = {
            name: self._create_filter(name, fromBlock="latest")
            for name in self.__filter_connections
        }

        while loaded_block < latest_block:
            for name, callback in self.__filter_connections.items():
                _filter = self._create_filter(
                    name, fromBlock=loaded_block, toBlock=loaded_block
                )
                for event in _filter.get_all_entries():
                    self.process_event(event, callback)
            self.__on_next_block_added(self.web3.eth.getBlock(loaded_block))
            loaded_block += 1
            latest_block = self.web3.eth.getBlock("latest")["number"]

            self._on_syncing_completed()

        while True:
            new_events = False
            for name, callback in self.__filter_connections.items():
                for event in self.filters[name].get_new_entries():
                    self.process_event(event, callback)
                    new_events = True

            if new_events:
                self._after_new_events_called()

            block_number = self.web3.eth.getBlock("latest")["number"]
            if block_number > self.last_processed_block:
                self.__on_next_block_added(self.web3.eth.getBlock(block_number))
                self.last_processed_block = block_number

            time.sleep(1)

    def get_last_block_data(self):
        return self._last_block_data

    def _on_next_block_added(self, block_data) -> None:
        ...

    def _after_new_events_called(self) -> None:
        ...

    def _on_syncing_completed(self) -> None:
        ...
