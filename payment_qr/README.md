# Payment QR assets

## Local QR (ABA / KHQR / bank, etc.)

Put screenshots of payment QRs in `payment_qr/local/`, named by **USD amount**:

```
payment_qr/local/30.png
payment_qr/local/40.png
payment_qr/local/50.png
payment_qr/local/100.png
...
```

Supported extensions: `.png`, `.jpg`, `.jpeg`, `.webp`.

At checkout the bot picks the **smallest QR amount ≥ order total**.
If the order is larger than every QR, it uses the largest available.

## USDT (optional QR)

Optional wallet QR image:

```
payment_qr/usdt.png
```

Set in Environment / `.env`:

```
USDT_WALLET=TYourTronOrOtherAddress
USDT_NETWORK=TRC20
USDT_QR_IMAGE=payment_qr/usdt.png
PAYMENT_QR_DIR=payment_qr/local
PAYMENT_QR_LABEL=Local QR
```

## Persistent order database (Render)

SQLite file is wiped on redeploy unless you mount a disk:

1. Render → service → Disks → add disk, mount path `/data`
2. Environment: `DATABASE_FILE=/data/orders.db`
