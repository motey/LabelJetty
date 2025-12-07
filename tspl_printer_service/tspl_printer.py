#!/usr/bin/env python3
from typing import List, Union, IO, Dict
from encodings.punycode import T
import os
from PIL import Image, ImageOps, ImageDraw, ImageFont, _typing
from usb.core import Device
import textwrap
import glob
from tspl_printer_connection import TSPLPrinterConnectionUSB
from pathlib import Path


class TSPLPrinter:
    """
    Minimal TSPL printer interface.
    Supports:
      - PNG printing (auto resize)
      - Basic markdown printing
      - FORMFEED (advance to next label)
    """

    def __init__(
        self,
        connection: TSPLPrinterConnectionUSB,
        label_width_mm: int = 100,
        label_height_mm: int = 30,
        dpi: int = 203,
        dry_run_mode: bool = False,
    ):
        """_summary_

        Args:
            width_mm (int, optional): _description_. Defaults to 40.
            height_mm (int, optional): _description_. Defaults to 30.
            dpi (int, optional): _description_. Defaults to 203.
            connection (TSPLPrinterConnection | bool, optional): Set a known `usb.core.Device` connection for a specific printer or True if oyu want to auto connect to the first device we can find or false if you want to use `list_available_printers`.`set_printer`. Defaults to False.
            dry_run_mode (bool, optional): _description_. Defaults to False.
        """

        self.connection = connection
        self.width_mm = label_width_mm
        self.height_mm = label_height_mm
        self.dpi = dpi
        self.dry_run_mode: bool = dry_run_mode

        # Compute pixel size of the label
        self.width_px = int((label_width_mm / 25.4) * dpi)
        self.height_px = int((label_height_mm / 25.4) * dpi)

    # ------------------------------------------------------------ #
    #  Low-level send function
    # ------------------------------------------------------------ #
    def _send(self, data: str):
        if self.dry_run_mode:
            print(data)
            return
        self.connection.send(data)

    def _send_many(self, data: Union[List[str], tuple[str, ...]]):
        if self.dry_run_mode:
            print(data)
            return
        self.connection.send_many(data)

    # ------------------------------------------------------------ #
    #  Basic TSPL commands
    # ------------------------------------------------------------ #

    def formfeed(self):
        """Advance to the next label."""
        self._send("FORMFEED\n")

    def cls(self):
        """Clear image buffer."""
        self._send("CLS\n")

    def print_label(self, copies=1):
        """Print out current buffered image."""
        self._send(f"PRINT {copies}\n")

    def set_reference_point(self, x: int = 0, y: int = 0):
        """
        Set the reference point (origin) for label printing.

        Args:
            x: X-axis reference point in dots (default: 0)
            y: Y-axis reference point in dots (default: 0)

        By default, many printers center content. Setting this to 0,0
        will align content to the top-left corner of the label.
        """
        self._send(f"REFERENCE {x},{y}\n")

    def set_shift(self, dots: int = 0):
        """
        Set vertical shift of the print position.

        Args:
            dots: Negative values move content up, positive moves down
        """
        self._send(f"SHIFT {dots}\n")

    def set_direction(self, direction: int = 0):
        """
        Set print direction.
        0 = no mirror, 1 = mirror
        """
        self._send(f"DIRECTION {direction}\n")

    def receive(self, length: int, timeout: int = 5000) -> bytes:
        """
        Read data from printer.

        Args:
            length: Number of bytes to read
            timeout: Timeout in milliseconds

        Returns:
            bytes: Data received from printer
        """
        if self.device is None:
            raise RuntimeError("No printer connected")

        # Typical USB printers use endpoint 0x81 for input
        # You may need to adjust this based on your printer
        endpoint = 0x81

        try:
            data = self.device.read(endpoint, length, timeout=timeout)
            return bytes(data)
        except Exception as e:
            raise TimeoutError(f"Failed to read from printer: {e}")

    def get_status(self) -> Dict:
        """
        Query printer status.

        Returns:
            dict: Status information with keys:
                - 'ready': bool - True if printer is ready
                - 'paper_jam': bool
                - 'paper_empty': bool
                - 'ribbon_empty': bool
                - 'printing': bool
                - 'paused': bool
                - 'error': bool
                - 'raw_status': bytes - Raw status byte
        """
        if self.dry_run_mode:
            return {
                "ready": True,
                "paper_jam": False,
                "paper_empty": False,
                "ribbon_empty": False,
                "printing": False,
                "paused": False,
                "error": False,
                "raw_status": b"\x00",
            }

        self._send("~!T\n")  # Request status
        response = self.connection.receive(1)  # Read 1 byte

        if not response:
            raise TimeoutError("No response from printer")

        status_byte = response[0]

        return {
            "ready": (status_byte & 0x01) == 0,  # Bit 0: 0=ready, 1=not ready
            "paper_jam": bool(status_byte & 0x02),  # Bit 1
            "paper_empty": bool(status_byte & 0x04),  # Bit 2
            "ribbon_empty": bool(status_byte & 0x08),  # Bit 3
            "printing": bool(status_byte & 0x10),  # Bit 4
            "paused": bool(status_byte & 0x20),  # Bit 5
            "error": bool(status_byte & 0x80),  # Bit 7: general error
            "raw_status": response,
        }

    def is_ready(self) -> bool:
        """
        Check if printer is ready to accept new print jobs.

        Returns:
            bool: True if ready, False otherwise
        """
        status = self.get_status()
        return status["ready"] and not status["error"]

    def wait_until_ready(self, timeout: float = 30, poll_interval: float = 0.5) -> bool:
        """
        Wait until printer is ready.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            bool: True if printer became ready, False if timeout
        """
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.is_ready():
                return True
            time.sleep(poll_interval)

        return False

    def get_error_message(self) -> str | None:
        """
        Get human-readable error message based on current status.

        Returns:
            str: Error message or "No errors" if printer is okay
        """
        status = self.get_status()

        if status["ready"] and not status["error"]:
            return None

        errors: List[str] = []
        if status["paper_jam"]:
            errors.append("Paper jam detected")
        if status["paper_empty"]:
            errors.append("Paper/label out")
        if status["ribbon_empty"]:
            errors.append("Ribbon out")
        if status["printing"]:
            errors.append("Currently printing")
        if status["paused"]:
            errors.append("Printer paused")
        if status["error"] and not errors:
            errors.append("Unknown error")
        if not status["ready"] and not errors:
            errors.append("Printer not ready")

        return "; ".join(errors) if errors else "Unknown status"

    # ------------------------------------------------------------ #
    # Convert PIL image → TSPL BITMAP command
    # ------------------------------------------------------------ #

    def _bitmap_tspl(self, img: Image.Image, x=0, y=0):
        """
        Convert a 1-bit Pillow image into TSPL BITMAP command bytes.
        """
        if img.mode != "1":
            raise ValueError("Image must be 1-bit monochrome")

        w, h = img.size
        width_bytes = w // 8
        pixels = img.tobytes()

        # TSPL BITMAP uses one byte per 8 pixels, MSB first
        header = f"BITMAP {x},{y},{width_bytes},{h},0,".encode("ascii")
        return header + pixels + b"\n"

    # ------------------------------------------------------------ #
    #  Public: Print a PNG on the label
    # ------------------------------------------------------------ #

    def print_png(
        self,
        png: _typing.StrOrBytesPath | IO[bytes],
        x: int = 0,
        y: int = 0,
        width: int = None,
        height: int = None,
    ):
        """
        Print a PNG image on the label.

        Args:
            png: Path to PNG file or file-like object
            x: X position on label (pixels)
            y: Y position on label (pixels)
            width: Optional target width in pixels. If None, uses original size.
            height: Optional target height in pixels. If None, uses original size.

        If both width and height are None, the image will be printed at its original
        size, or resized to fit the label if it's too large (maintaining aspect ratio).
        If only width or height is specified, the other dimension is calculated to
        maintain aspect ratio.
        """
        # Load image
        img = Image.open(png)

        # Determine target size
        if width is None and height is None:
            # No size specified - use original or fit to label if too large
            if img.width > self.width_px or img.height > self.height_px:
                # Image is too large, resize to fit label
                img.thumbnail((self.width_px, self.height_px), Image.Resampling.LANCZOS)
            # else: keep original size
        elif width is not None and height is not None:
            # Both dimensions specified - resize to exact size
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        elif width is not None:
            # Only width specified - calculate height to maintain aspect ratio
            aspect_ratio = img.height / img.width
            new_height = int(width * aspect_ratio)
            img = img.resize((width, new_height), Image.Resampling.LANCZOS)
        else:
            # Only height specified - calculate width to maintain aspect ratio
            aspect_ratio = img.width / img.height
            new_width = int(height * aspect_ratio)
            img = img.resize((new_width, height), Image.Resampling.LANCZOS)

        # Convert to grayscale first
        img = img.convert("L")

        # Apply proper dithering for better quality on thermal printers
        img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

        # Ensure image width is a multiple of 8 (required for TSPL BITMAP)
        if img.width % 8 != 0:
            new_width = ((img.width + 7) // 8) * 8
            padded = Image.new("1", (new_width, img.height), 1)  # 1 = white
            padded.paste(img, (0, 0))
            img = padded

        # Build TSPL job
        self.cls()
        bitmap_cmd = self._bitmap_tspl(img, x, y)
        self._send(f"SIZE {self.width_mm} mm,{self.height_mm} mm\n")
        self._send(bitmap_cmd)
        self.print_label()

    # ------------------------------------------------------------ #
    #  Public: Print basic markdown
    # ------------------------------------------------------------ #

    def print_markdown(
        self,
        md_text,
        x=10,
        y=10,
        font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        """
        Very basic markdown → text rendering:
          # Heading
          ## Subheading
          * bullet lists
          **bold** becomes uppercase
          normal paragraphs
        """
        font = ImageFont.truetype(font_path, 24)

        # Create a blank label canvas
        img = Image.new("1", (self.width_px, self.height_px), 1)
        draw = ImageDraw.Draw(img)

        offset = y
        line_height = 28

        for line in md_text.splitlines():
            line = line.strip()

            if not line:
                offset += line_height
                continue

            # Headings
            if line.startswith("## "):
                txt = line[3:]
                draw.text((x, offset), txt.upper(), font=font, fill=0)
                offset += line_height
                continue

            if line.startswith("# "):
                txt = line[2:]
                draw.text((x, offset), txt.upper(), font=font, fill=0)
                offset += line_height
                continue

            # Bullet list
            if line.startswith("* "):
                txt = "• " + line[2:]
            else:
                txt = line

            # Bold **text**
            if "**" in txt:
                txt = txt.replace("**", "").upper()

            # Wrap text
            max_chars = self.width_px // 13
            for chunk in textwrap.wrap(txt, max_chars):
                draw.text((x, offset), chunk, font=font, fill=0)
                offset += line_height

        # Convert to printer commands
        self.cls()
        bitmap_cmd = self._bitmap_tspl(img, 0, 0)
        self._send(bitmap_cmd)
        self.print_label()

    def print_barcode(
        self,
        data: str,
        x: int = None,
        y: int = None,
        barcode_type: str = "128",
        height: int = None,
        readable: bool = True,
        rotation: int = 0,
        narrow_bar: int = 2,
        wide_bar: int = 6,
    ):
        """
        Print a barcode on the label.

        Args:
            data: Barcode data to encode
            x: X position in pixels (default: centered horizontally)
            y: Y position in pixels (default: 10% from top)
            barcode_type: Barcode type. Options:
                - "128" (Code 128, default - good for alphanumeric)
                - "128M" (Code 128 Manual)
                - "EAN13" (EAN-13, requires 12-13 digits)
                - "EAN8" (EAN-8, requires 7-8 digits)
                - "39" (Code 39)
                - "93" (Code 93)
                - "UPCA" (UPC-A, requires 11-12 digits)
                - "UPCE" (UPC-E, requires 6-8 digits)
                - "I25" (Interleaved 2 of 5)
            height: Barcode height in pixels (default: 40% of label height)
            readable: Show human-readable text below barcode
            rotation: Rotation angle (0, 90, 180, 270)
            narrow_bar: Width of narrow bar in dots (1-10, default: 2)
            wide_bar: Width of wide bar in dots (2-30, default: 6)
        """
        # Set defaults based on label size
        if height is None:
            height = int(self.height_px * 0.4)  # 40% of label height

        if x is None:
            # Center horizontally (approximate, depends on barcode width)
            x = int(self.width_px * 0.1)  # Start at 10% from left

        if y is None:
            y = int(self.height_px * 0.1)  # 10% from top

        # Ensure height is reasonable
        height = min(height, int(self.height_px * 0.8))

        human_readable = 1 if readable else 0

        self.cls()
        self._send(
            f'BARCODE {x},{y},"{barcode_type}",{height},{human_readable},'
            f'{rotation},{narrow_bar},{wide_bar},"{data}"\n'
        )
        self.print_label()

    def print_qrcode(
        self,
        data: str,
        x: int = None,
        y: int = None,
        ecc_level: str = "M",
        cell_width: int = None,
        mode: str = "A",
        rotation: int = 0,
    ):
        """
        Print a QR code on the label.

        Args:
            data: Data to encode in QR code (max ~2953 bytes for alphanumeric)
            x: X position in pixels (default: centered)
            y: Y position in pixels (default: centered)
            ecc_level: Error correction level:
                - "L" (Low, 7% recovery)
                - "M" (Medium, 15% recovery, default)
                - "Q" (Quality, 25% recovery)
                - "H" (High, 30% recovery)
            cell_width: Width of each QR code cell in dots (default: auto-sized to fit label)
            mode: QR code mode:
                - "A" (Auto, default)
                - "M" (Manual)
            rotation: Rotation angle (0, 90, 180, 270)
        """
        # Auto-size QR code to fit label nicely
        if cell_width is None:
            # QR codes are typically 21-177 modules depending on data
            # Estimate: use 50% of the smaller dimension
            min_dimension = min(self.width_px, self.height_px)
            # Assume ~30 modules for typical data, scale cell width accordingly
            cell_width = max(2, int(min_dimension * 0.5 / 30))
            # Cap at reasonable size
            cell_width = min(cell_width, 10)

        # Calculate approximate QR code size for centering
        # Estimate ~30 modules for typical QR code
        estimated_size = cell_width * 30

        if x is None:
            x = max(0, (self.width_px - estimated_size) // 2)

        if y is None:
            y = max(0, (self.height_px - estimated_size) // 2)

        self.cls()
        self._send(
            f'QRCODE {x},{y},{ecc_level},{cell_width},{mode},{rotation},"{data}"\n'
        )
        self.print_label()

    def print_barcode_with_text(
        self,
        barcode_data: str,
        text: str = None,
        barcode_type: str = "128",
        font_size: int = 3,
    ):
        """
        Print a barcode with custom text above or below it.
        Automatically layouts barcode and text on the label.

        Args:
            barcode_data: Data to encode in barcode
            text: Additional text to print (default: None, only barcode printed)
            barcode_type: Barcode type (see print_barcode for options)
            font_size: Font size for text (1-8)
        """
        self.cls()

        # Calculate layout
        text_height = 20 * font_size if text else 0
        barcode_height = int((self.height_px - text_height - 20) * 0.8)

        # Print text at top if provided
        if text:
            text_y = 10
            self._send(f'TEXT 10,{text_y},"3",0,1,1,"{text}"\n')

        # Print barcode below text
        barcode_y = text_height + 10 if text else int(self.height_px * 0.1)
        barcode_x = int(self.width_px * 0.1)

        self._send(
            f'BARCODE {barcode_x},{barcode_y},"{barcode_type}",{barcode_height},1,'
            f'0,2,6,"{barcode_data}"\n'
        )

        self.print_label()

    def print_qrcode_with_text(
        self,
        qr_data: str,
        text: str = None,
        text_position: str = "bottom",
        ecc_level: str = "M",
        font_size: int = 3,
    ):
        """
        Print a QR code with text.

        Args:
            qr_data: Data to encode in QR code
            text: Text to display (default: None)
            text_position: "top" or "bottom" (default: "bottom")
            ecc_level: Error correction level (L, M, Q, H)
            font_size: Font size for text (1-8)
        """
        self.cls()

        # Calculate layout
        text_height = 20 * font_size if text else 0
        available_height = self.height_px - text_height - 20

        # Size QR code to fit remaining space
        min_dimension = min(self.width_px, available_height)
        cell_width = max(2, int(min_dimension * 0.6 / 30))
        cell_width = min(cell_width, 10)

        estimated_qr_size = cell_width * 30
        qr_x = max(0, (self.width_px - estimated_qr_size) // 2)

        if text:
            if text_position == "top":
                text_y = 10
                qr_y = text_height + 10
            else:  # bottom
                qr_y = 10
                text_y = qr_y + estimated_qr_size + 10

            text_x = 10
            self._send(f'TEXT {text_x},{text_y},"3",0,1,1,"{text}"\n')
        else:
            qr_y = max(0, (self.height_px - estimated_qr_size) // 2)

        self._send(f'QRCODE {qr_x},{qr_y},{ecc_level},{cell_width},A,0,"{qr_data}"\n')

        self.print_label()
