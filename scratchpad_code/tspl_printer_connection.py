import traceback
import usb.core
import usb.util
import time
from typing import Optional, List, Union, cast
from usb.core import Device, Endpoint, Configuration, Interface, USBError
import glob
import os


class TSPLPrinterConnectionUSB:
    """
    Automatically detects a TSPL printer by probing USB devices and sending
    a harmless TSPL query command (~!T). Maintains connection and allows
    sending TSPL commands via .send().
    """

    def __init__(
        self,
        vendor: Optional[int | str] = None,
        product: Optional[int | str] = None,
        retry_interval: float = 1.0,
        auto_connect: bool = False,
    ) -> None:
        if isinstance(vendor, str):
            vendor = int(vendor, 16)
        else:
            vendor = int(vendor)

        if isinstance(product, str):
            product = int(product, 16)
        else:
            product = int(product)
        self.vendor: Optional[int] = vendor
        self.product: Optional[int] = product
        self.dev: Optional[Device] = None
        self.ep_out: Optional[Endpoint] = None
        self.ep_in: Optional[Endpoint] = None
        self.retry_interval: float = retry_interval
        if auto_connect:
            self.connect()

    # ---------------------------------------------------------
    #  List all TSPL printers on USB
    # ---------------------------------------------------------
    @classmethod
    def list_printers(cls) -> List[Device]:
        printers: List[Device] = []
        for dev in usb.core.find(find_all=True):
            if cls.probe_tspl(dev):
                printers.append(cast(Device, dev))
        return printers

    # ---------------------------------------------------------
    #  Probe a USB device to check if it's a TSPL printer
    # ---------------------------------------------------------
    @classmethod
    def probe_tspl(cls, dev: Device, raise_if_failed: bool = False) -> bool:
        try:
            # Set configuration
            try:
                dev.set_configuration()
            except usb.core.USBError as e:
                if e.backend_error_code == -3:
                    print(
                        f"Access denied (insufficient permissions) for device {dev._str()}"
                    )
                    return
                else:
                    raise e
            cfg: Configuration = dev.get_active_configuration()
            intf: Interface = cfg[(0, 0)]

            # Find OUT endpoint
            ep_out: Optional[Endpoint] = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_OUT,
            )

            # Find IN endpoint
            ep_in: Optional[Endpoint] = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_IN,
            )

            if not ep_out or not ep_in:
                return False

            # Send harmless "request printer model" command
            ep_out.write(b"~!T\n")

            # Try to read a response
            # TSPL usually replies in under 200ms
            resp: bytes = ep_in.read(64, timeout=300)

            # Decode response text
            txt: str = bytes(resp).decode(errors="ignore").strip()

            # TSPL returns printable ASCII
            if txt:
                return True

        except Exception as e:
            if raise_if_failed:
                raise e
            else:
                if isinstance(dev, Device):
                    print(f"Could not prope device {dev._str()}. Error {e}")
                else:
                    traceback.print_exc()
                return False

        return False

    # ---------------------------------------------------------
    #  Automatically locate a TSPL printer on USB
    # ---------------------------------------------------------
    def auto_detect(self) -> Optional[Device]:
        for dev in usb.core.find(find_all=True):
            if self.probe_tspl(dev):
                return dev
        return None

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


import os
import glob


class USBLabelScanner:
    def read_attr(self, path):
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except:
            return None

    def get_interfaces(self, devpath):
        interfaces = []
        for iface in glob.glob(os.path.join(devpath, devpath.split("/")[-1] + ":*")):
            interfaces.append(
                {
                    "interface_path": iface,
                    "bInterfaceClass": self.read_attr(
                        os.path.join(iface, "bInterfaceClass")
                    ),
                    "bInterfaceSubClass": self.read_attr(
                        os.path.join(iface, "bInterfaceSubClass")
                    ),
                    "bInterfaceProtocol": self.read_attr(
                        os.path.join(iface, "bInterfaceProtocol")
                    ),
                    "driver": os.path.basename(
                        os.readlink(os.path.join(iface, "driver"))
                    )
                    if os.path.exists(os.path.join(iface, "driver"))
                    else None,
                }
            )
        return interfaces

    def scan(self):
        devices = []
        for path in glob.glob("/sys/bus/usb/devices/*"):
            if not os.path.exists(os.path.join(path, "idVendor")):
                continue  # skip hubs etc.

            dev = {
                "path": path,
                "idVendor": self.read_attr(os.path.join(path, "idVendor")),
                "idProduct": self.read_attr(os.path.join(path, "idProduct")),
                "manufacturer": self.read_attr(os.path.join(path, "manufacturer")),
                "product": self.read_attr(os.path.join(path, "product")),
                "serial": self.read_attr(os.path.join(path, "serial")),
                "bDeviceClass": self.read_attr(os.path.join(path, "bDeviceClass")),
                "bDeviceSubClass": self.read_attr(
                    os.path.join(path, "bDeviceSubClass")
                ),
                "bDeviceProtocol": self.read_attr(
                    os.path.join(path, "bDeviceProtocol")
                ),
                "speed": self.read_attr(os.path.join(path, "speed")),
                "bMaxPower": self.read_attr(os.path.join(path, "bMaxPower")),
                "interfaces": self.get_interfaces(path),
            }
            devices.append(dev)
        return devices

    def heuristic_is_label_printer(self, dev):
        """
        Heuristic detection of label printers.
        Non-invasive and permission-free.
        """

        # Vendor or product name hints
        keywords = [
            "label",
            "printer",
            "barcode",
            "thermal",
            "tsc",
            "xprinter",
            "argox",
            "godex",
            "postek",
        ]

        name = (
            " ".join(
                [str(dev.get("manufacturer") or ""), str(dev.get("product") or "")]
            )
        ).lower()

        if any(k in name for k in keywords):
            return True

        # Interface class heuristic (printer class, vendor-specific, CDC)
        for iface in dev["interfaces"]:
            cls = iface.get("bInterfaceClass")
            if cls in ("07", "ff", "02"):  # printer, vendor-specific, serial
                return True

        # High power draw (printers often pull 200–500mA)
        try:
            power = int(dev.get("bMaxPower", "0").replace("mA", ""))
            if power >= 200:
                return True
        except:
            pass

        return False


import serial
import serial.tools.list_ports


class TSPLPrinterConnectionSerial:
    def __init__(self, baudrates=None, timeout=0.5):
        # Typical TSPL baud rates
        self.baudrates = baudrates or [9600, 115200, 19200]
        self.timeout = timeout

    def is_tspl_printer(self, port):
        """
        Try to detect a TSPL printer on a given serial port.
        Returns model name on success, None otherwise.
        """

        for baud in self.baudrates:
            try:
                with serial.Serial(port, baud, timeout=self.timeout) as ser:
                    # Flush buffers
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()

                    return self.detect_tspl(ser)

            except (serial.SerialException, OSError):
                continue

        return None

    def detect_tspl(self, ser):
        """
        Robust TSPL detection sequence.
        Returns model name or True if TSPL, None if not.
        """

        def send(cmd):
            ser.write(cmd)
            return ser.read(128).decode(errors="ignore").strip()

        # Step 1 — safe clear
        send(b"CLS\r\n")

        # Step 2 — invalid command test
        resp = send(b"XYZ123\r\n")
        if "ERROR" in resp.upper() or "INVALID" in resp.upper():
            return True  # TSPL signature

        # Step 3 — GET STATUS
        resp = send(b"GET STATUS\r\n")
        if resp and len(resp) < 64 and resp != "XYZ123":
            return True

        # Step 4 — GET MODEL (final attempt)
        resp = send(b"GET MODEL\r\n")
        if resp and len(resp) < 64:
            return resp

        return None

    def scan(self):
        """
        Scan all serial ports and return list of detected TSPL printers.
        Returns:
            List of dicts: [{ "port": "/dev/ttyUSB0", "baud": 9600, "model": "XP-420B" }]
        """

        printers = []
        ports = serial.tools.list_ports.comports()

        for p in ports:
            print(p)
            model = self.is_tspl_printer(p.device)
            if model:
                printers.append(
                    {"port": p.device, "description": p.description, "model": model}
                )

        return printers
