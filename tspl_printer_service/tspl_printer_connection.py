import traceback
import usb.core
import usb.util
import time
from typing import Optional, List, Union, cast, Self
from usb.core import Device, Endpoint, Configuration, Interface, USBError
import glob
import os


class TSPLPrinterConnectionUSB:
    """
    Automatically detects a TSPL printer by probing USB devices and sending
    a harmless TSPL query command (~!T). Maintains connection and allows
    sending TSPL commands via .send().
    """

    # -------------------------
    # --- Lookup: VID / PID ---
    # -------------------------
    @classmethod
    def by_vendor_and_product_id(
        cls, vendor: Optional[int | str] = None, product: Optional[int | str] = None
    ) -> Self:
        if vendor is None and product is None:
            raise ValueError("Must specify vendor and/or product ID")

        # Convert hex strings
        if isinstance(vendor, str):
            vendor = int(vendor, 16)
        if isinstance(product, str):
            product = int(product, 16)

        devices = usb.core.find(
            find_all=True,
            idVendor=vendor if vendor is not None else None,
            idProduct=product if product is not None else None,
        )

        if devices is None:
            raise ValueError("No USB devices found matching given VID/PID")

        # Return the first match
        for dev in devices:
            return cls(dev)

        raise ValueError("No USB devices found matching given VID/PID")

    # -----------------------------
    # --- Lookup: Bus + Address ---
    # -----------------------------
    @classmethod
    def by_bus_and_device_id(
        cls, bus: Optional[int | str] = None, device_id: Optional[int | str] = None
    ) -> Self:
        if bus is None or device_id is None:
            raise ValueError("bus and device_id must both be provided")

        if isinstance(bus, str):
            bus = int(bus)
        if isinstance(device_id, str):
            device_id = int(device_id)

        for dev in usb.core.find(find_all=True):
            if dev.bus == bus and dev.address == device_id:
                return cls(dev)

        raise ValueError(f"No USB device found at bus={bus} device={device_id}")

    # -------------------------
    # --- Lookup: Serial#  ---
    # -------------------------
    @classmethod
    def by_serial(cls, serial: str) -> Self:
        if not serial:
            raise ValueError("Serial cannot be empty")

        for dev in usb.core.find(find_all=True):
            try:
                dev_serial = usb.util.get_string(dev, dev.iSerialNumber)
            except Exception:
                continue

            if dev_serial == serial:
                return cls(dev)

        raise ValueError(f"No USB device found with serial={serial}")

    # ----------------------------
    # --- Lookup: Port Path     ---
    # ----------------------------
    @classmethod
    def by_port(cls, port_path: List[int] | str) -> Self:
        """
        port_path may be:
            [3, 1, 2]
        or a string "3-1-2"
        """

        if isinstance(port_path, str):
            # Convert "3-1-2" → [3,1,2]
            port_path = [int(x) for x in port_path.split("-")]

        for dev in usb.core.find(find_all=True):
            if dev.port_numbers == port_path:
                return cls(dev)

        raise ValueError(f"No USB device found at port path {port_path}")

    # -----------------------------
    # --- Helper (Optional Use) ---
    # -----------------------------
    @staticmethod
    def find_device_by_bus_and_address(bus, address):
        for dev in usb.core.find(find_all=True):
            if dev.bus == bus and dev.address == address:
                return dev
        return None

    def __init__(
        self,
        usb_device: Device,
        retry_interval: float = 1.0,
    ) -> None:
        self.dev: Device = usb_device
        self.ep_out: Optional[Endpoint] = None
        self.ep_in: Optional[Endpoint] = None
        self.retry_interval: float = retry_interval

    # ---------------------------------------------------------
    #  Connect (auto-detect if vendor/product not given)
    # ---------------------------------------------------------
    def connect(self) -> bool:
        while True:
            try:
                if self.vendor and self.product:
                    # Manual device selection
                    self.dev = usb.core.find(
                        idVendor=self.vendor, idProduct=self.product
                    )
                    if self.dev is None:
                        raise ValueError(
                            f"can not find USB device at {self.vendor}:{self.product}"
                        )

                else:
                    # Auto-detect TSPL printer
                    print("Searching for TSPL printer...")
                    self.dev = self.auto_detect()

                if self.dev is None:
                    print("No TSPL printer found. Waiting...")
                    time.sleep(self.retry_interval)
                    continue

                # Detach any kernel drivers
                try:
                    if self.dev.is_kernel_driver_active(0):
                        self.dev.detach_kernel_driver(0)
                except Exception:
                    pass

                self.dev.set_configuration()
                cfg: Configuration = self.dev.get_active_configuration()
                intf: Interface = cfg[(0, 0)]

                # Set endpoints
                self.ep_out = usb.util.find_descriptor(
                    intf,
                    custom_match=lambda e: usb.util.endpoint_direction(
                        e.bEndpointAddress
                    )
                    == usb.util.ENDPOINT_OUT,
                )

                self.ep_in = usb.util.find_descriptor(
                    intf,
                    custom_match=lambda e: usb.util.endpoint_direction(
                        e.bEndpointAddress
                    )
                    == usb.util.ENDPOINT_IN,
                )

                if not self.ep_out:
                    raise RuntimeError("USB OUT endpoint not found.")
                if not self.ep_in:
                    raise RuntimeError("USB IN endpoint not found.")

                print("Connected to TSPL printer.")
                return True

            except Exception as e:
                print(f"Connection error: {e}. Retrying...")
                time.sleep(self.retry_interval)

    # ---------------------------------------------------------
    #  Send a TSPL command (auto reconnect if needed)
    # ---------------------------------------------------------
    def send(self, cmd: str | bytes) -> None:
        if not self.dev:
            self.connect()

        # Ensure cmd is bytes
        if isinstance(cmd, str):
            data: bytes = (cmd.strip() + "\n").encode("ascii")
        else:
            data = cmd.strip(b"\n") + b"\n"

        try:
            self.ep_out.write(data)

        except usb.core.USBError:
            print("USB write failed — reconnecting...")
            self.connect()
            self.ep_out.write(data)

    # ---------------------------------------------------------
    #  Send multiple commands
    # ---------------------------------------------------------
    def send_many(self, commands: Union[List[str], tuple[str, ...]]) -> None:
        for c in commands:
            self.send(c)
