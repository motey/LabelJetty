# Setup guide

Going from nothing to a printing label, in order. The classic setup is a Raspberry Pi
next to the printer, but any Linux host with a USB port works.

1. [Get a printer](#1-get-a-printer)
2. [Prepare the host](#2-prepare-the-host)
3. [Find your printer](#3-find-your-printer)
4. [Grant USB access](#4-grant-usb-access)
5. [Run LabelJetty](#5-run-labeljetty)
6. [Verify](#6-verify)
7. [Next steps](#next-steps)

## 1. Get a printer

You need a USB printer that speaks **TSPL** (~203 dpi is typical). The reference device is
a cheap **Vretti 420B** (USB id `2d37:62de`). Any genuine TSPL-over-USB printer should
work. See [Hardware](hardware.md) for what to buy and which clones are equivalent.

## 2. Prepare the host

LabelJetty ships as a Docker image, so the only requirement is **Docker** with Compose
(`docker compose version` to check; [install docs](https://docs.docker.com/engine/install/)).
The image bundles everything else it needs (libusb, the DejaVu font).

> Prefer not to use Docker? You can run it straight from PyPI or a source checkout instead
> see [Running without Docker](advanced-usage.md#running-without-docker).

## 3. Find your printer

Plug the printer in and list USB devices:

```sh
lsusb
```

Find your label printer, e.g.:

```
Bus 001 Device 015: ID 2d37:62de Zhuhai Poskey Technology Co.,Ltd 420B
```

The **vendor:product id** here is `2d37:62de` - note it down. You will use it as
`PRINTER_USB=vid:2d37:pid:62de` below. This `vid:pid` form is the most robust selector
because it survives replugging; other forms are listed in
[Configuration](configuration.md#printer_usb-selector-forms).

## 4. Grant USB access

By default a normal user (and the container) cannot open the USB device, which fails with:

```
usb.core.USBError: [Errno 13] Access denied (insufficient permissions)
```

Fix it with a udev rule that gives the `plugdev` group access (most desktop users are
already in `plugdev` - check with `groups`). Replace the ids with **your** printer's:

```sh
sudo tee /etc/udev/rules.d/99-tspl-printer.rules >/dev/null <<'EOF'
# TSPL label printer - allow plugdev group to access it over raw USB
SUBSYSTEM=="usb", ATTRS{idVendor}=="2d37", ATTRS{idProduct}=="62de", MODE="0660", GROUP="plugdev"
EOF

# Reload rules and re-trigger (or just unplug/replug the printer)
sudo udevadm control --reload-rules
sudo udevadm trigger
```

If you are not in `plugdev`, add yourself and log out/in:

```sh
sudo usermod -aG plugdev "$USER"
```

This rule lives on the **host** and governs the device for Docker too: the container's
`--device=/dev/bus/usb` only passes the device through, the host still controls its
permissions.

> Just want a one-off local test without the rule? Run the command with `sudo` (e.g.
> `sudo uv run labeljetty-testbench status`). The udev rule is the proper, persistent
> solution for an always-on box.

## 5. Run LabelJetty

A ready-made [`docker-compose.yml`](../docker-compose.yml) is in the repo. The minimal
form:

```yaml
services:
  labeljetty:
    image: motey/labeljetty:latest
    restart: unless-stopped
    ports:
      - "8888:8888"
    devices:
      - /dev/bus/usb:/dev/bus/usb      # the printer's USB bus
    environment:
      PRINTER_USB: vid:2d37:pid:62de   # from step 3; the only required setting
    volumes:
      - ./data:/data                   # persists the job DB + stored images
```

```sh
docker compose up -d
```

Then open **http://localhost:8888/**. Match your label stock by also setting
`DEFAULT_LABEL_WIDTH_MM` / `DEFAULT_LABEL_HEIGHT_MM` / `DEFAULT_DPI`; every other setting is
optional and documented in [Configuration](configuration.md).

## 6. Verify

Print the built-in alignment pattern - the surest test that the printer works and the label
geometry is right:

```sh
docker compose exec labeljetty labeljetty-testbench pattern
```

<details>
<summary>Not using Compose? - docker / uv / python</summary>

```sh
# docker
docker exec labeljetty labeljetty-testbench pattern

# uv (from a source checkout)
uv run labeljetty-testbench pattern

# python (venv with `pip install labeljetty`)
python -m labeljetty.testbench pattern
```

</details>

A correctly configured label shows a border flush to all four edges, with the millimetre
ruler ticks landing on whole millimetres. Adjust `--width-mm` / `--height-mm` / `--dpi` (or
the `DEFAULT_LABEL_*` env vars) to match your stock. More testbench commands are in
[Developing](developing.md#real-world-print-tests-with-the-testbench).

> Many cheap clones are **write-only for status**: they print fine but never answer status
> queries. That is expected and does not affect printing, see
> [Status reading is optional](configuration.md#status-reading-is-optional).

## Next steps

- **[Configuration](configuration.md)** - every setting, and which to set for your stock.
- **[Authentication](advanced-usage.md#authentication)** - the default is **no auth**; turn
  it on before exposing the service beyond a trusted LAN.
- **[Homebox integration](advanced-usage.md#homebox-integration)** - print inventory labels.
- **[REST API](advanced-usage.md#the-rest-api)** - drive it from scripts and other machines.
