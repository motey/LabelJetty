import os
import glob
import errno
import subprocess
import re
import textwrap


class TSPLDetect:
    USB_KEYWORDS = (
        "xprinter",
        "vretti",
        "tsc",
        "gprinter",
        "barcode",
        "label",
        "thermal",
        "printer",
    )

    @staticmethod
    def _is_usb_printer_by_sysfs(devpath):
        """
        Check if the device node belongs to a USB printer
        by walking sysfs nodes and reading product/manufacturer.
        """
        base = os.path.basename(devpath)

        # Try standard sysfs path
        sysnode = f"/sys/class/usb/{base}"

        # If that doesn't exist, try scanning class directories
        if not os.path.exists(sysnode):
            for p in glob.glob("/sys/class/usb/*"):
                if os.path.basename(p) == base:
                    sysnode = p
                    break

        if not os.path.exists(sysnode):
            return False

        try:
            real = os.path.realpath(sysnode)
        except Exception:
            return False

        # Walk upward, checking attributes like product/manufacturer
        cur = real
        while cur and cur != "/":
            for attribute in ("product", "manufacturer", "idVendor", "idProduct"):
                path = os.path.join(cur, attribute)
                if os.path.exists(path):
                    try:
                        text = (
                            open(path, "rb").read(200).decode(errors="ignore").lower()
                        )
                    except Exception:
                        text = ""

                    if any(k in text for k in TSPLDetect.USB_KEYWORDS):
                        return True

            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent

        return False

    @staticmethod
    def generate_udev_rule(devpath: str) -> str | None:
        """
        Generate a udev rule snippet for the given USB printer device.
        Returns a string you can directly put in /etc/udev/rules.d/99-tspl-printer.rules
        """
        try:
            # Use udevadm with -a to walk up the device chain and get attributes
            output = subprocess.check_output(
                ["udevadm", "info", "-a", "-n", devpath],
                text=True,
                stderr=subprocess.DEVNULL,
            )

            vid = None
            pid = None

            # Parse the output for idVendor and idProduct attributes
            # These appear as ATTRS{idVendor}=="xxxx" in the output
            for line in output.splitlines():
                line = line.strip()
                if "ATTRS{idVendor}" in line:
                    match = re.search(r'ATTRS\{idVendor\}=="([^"]+)"', line)
                    if match and not vid:  # Take the first (closest) match
                        vid = match.group(1)
                elif "ATTRS{idProduct}" in line:
                    match = re.search(r'ATTRS\{idProduct\}=="([^"]+)"', line)
                    if match and not pid:  # Take the first (closest) match
                        pid = match.group(1)

                # Stop once we have both
                if vid and pid:
                    break

            if not vid or not pid:
                return None

            # Generate the udev rule
            rule = textwrap.dedent(f"""
                                   # Generated udev rule for TSPL label printer at {devpath}
                                   # Vendor ID: {vid}, Product ID: {pid}
                                   SUBSYSTEM=="usb", ATTR{{idVendor}}=="{vid}", ATTR{{idProduct}}=="{pid}", MODE="0666", GROUP="lp"
                                    """)
            return rule

        except Exception:
            return None

    @staticmethod
    def get_udev_install_command(generate_udev_rule: str) -> str:
        """
        Generate a complete bash command that the user can copy-paste
        to install the udev rule.

        Args:
            generate_udev_rule: The udev rule content (can be multiline)

        Returns:
            A bash command string
        """
        # Escape backslashes and % so printf doesn’t misinterpret them
        rule = generate_udev_rule.replace("\\", "\\\\").replace("%", "%%")

        # Replace real newlines with \n so the command stays one line
        rule = rule.replace("\n", "\\n")

        # Use %b so printf interprets \n as actual newline
        bash_command = (
            f"sudo bash -c \"printf '%b' '{rule}' > /etc/udev/rules.d/99-tspl-printer.rules "
            f'&& udevadm control --reload-rules && udevadm trigger"'
        )

        return bash_command

    @staticmethod
    def _try_open_nonblocking(devpath):
        """
        Attempt to open device with O_NONBLOCK.
        Returns:
            (ok: bool, permission_issue: bool)
        """
        try:
            fd = os.open(devpath, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
            return True, False
        except OSError as e:
            if e.errno == errno.EACCES:
                return True, True  # exists but no permission
            return False, False

    @staticmethod
    def detect_device():
        """
        Detect a TSPL-compatible USB label printer.

        Returns:
            str: device path, e.g. "/dev/usb/lp8"

        Raises:
            PermissionError: found a printer but user lacks permission
            RuntimeError:    no printer found
        """
        candidates = sorted(glob.glob("/dev/usb/lp*")) + sorted(
            glob.glob("/dev/ttyUSB*")
        )

        # 1. Direct probing with non-blocking open
        for dev in candidates:
            ok, perm = TSPLDetect._try_open_nonblocking(dev)

            if ok:
                if perm:
                    error_message_hint = (
                        f"\n\nFound a label printer at {dev}, but you lack permission.\n\n"
                        f"Fix:\n"
                        f"    sudo usermod -aG lp $USER\n"
                        f"Then log out and back in.\n"
                    )
                    udev_rule_hint = TSPLDetect.generate_udev_rule(dev)
                    if udev_rule_hint:
                        error_message_hint = error_message_hint + (
                            f"Maybe you also need to a create udev rule for the printer:\n"
                            f"     {TSPLDetect.get_udev_install_command(TSPLDetect.generate_udev_rule(dev))}"
                        )

                    raise PermissionError(error_message_hint)

                # Prefer devices whose sysfs description matches printers
                if TSPLDetect._is_usb_printer_by_sysfs(dev):
                    return dev

                # Accept first working device if we cannot confirm metadata
                return dev

        # 2. Fallback: check USB sysfs for known printers and map to /dev
        for usbdev in glob.glob("/sys/bus/usb/devices/*"):
            product = ""
            manufacturer = ""

            try:
                product = (
                    open(os.path.join(usbdev, "product"), "rb")
                    .read(200)
                    .decode(errors="ignore")
                    .lower()
                )
            except Exception:
                pass
            try:
                manufacturer = (
                    open(os.path.join(usbdev, "manufacturer"), "rb")
                    .read(200)
                    .decode(errors="ignore")
                    .lower()
                )
            except Exception:
                pass

            if any(
                k in (product + " " + manufacturer) for k in TSPLDetect.USB_KEYWORDS
            ):
                devnodes = sorted(glob.glob("/dev/usb/lp*")) + sorted(
                    glob.glob("/dev/ttyUSB*")
                )
                if devnodes:
                    return devnodes[0]

        # 3. Nothing found
        raise RuntimeError("No TSPL-compatible label printer found.")
