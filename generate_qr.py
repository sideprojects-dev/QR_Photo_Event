import qrcode
from PIL import Image

# The URL of your live app
URL = "https://qr-photo-event.onrender.com"

# Generate QR code
qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=10,
    border=4,
)
qr.add_data(URL)
qr.make(fit=True)

# Create image
img = qr.make_image(fill_color="black", back_color="white")
img.save("qr_nunta.png")

print(f"QR: qr_nunta.png")
print(f"   URL: {URL}")