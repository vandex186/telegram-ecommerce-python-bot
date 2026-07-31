# Payment QR assets

Both payment methods use **QR images only** (address + amount are encoded in the QR).
Name each file by **USD amount**:

```
payment_qr/usdt/30.png
payment_qr/usdt/50.png
payment_qr/usdt/100.png

payment_qr/local/30.png
payment_qr/local/50.png
payment_qr/local/100.png
```

Supported extensions: `.png`, `.jpg`, `.jpeg`, `.webp`.

At checkout the bot picks the **smallest QR amount ≥ order total**.
If the order is larger than every QR, it uses the largest available.

## Optional env (defaults shown)

```
PAYMENT_USDT_QR_DIR=payment_qr/usdt
PAYMENT_QR_DIR=payment_qr/local
PAYMENT_QR_LABEL=ABA QR
DATABASE_FILE=/data/orders.db
```

## Persistent order database (Render)

SQLite is wiped on redeploy unless you mount a disk:

1. Render → service → Disks → add disk, mount path `/data`
2. Environment: `DATABASE_FILE=/data/orders.db`
