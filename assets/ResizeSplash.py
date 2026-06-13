from PIL import Image

image = Image.open('assets\\splash_base.bmp')
# by default pyinstaller max is (760, 480)
max_width = 400
max_height = 300
target_width = image.width
target_height = image.height

if(image.width > max_width):
    target_width = max_width
    # Calculate target height based on original aspect ratio
    percentage = target_width / float(image.width)
    target_height = int(float(image.height) * percentage)

# now make sure it fits...
if(target_height > max_height):
    target_height = max_height
    # Calculate target width based on original aspect ratio
    percentage = target_height / float(image.height)
    target_width = int(float(image.width) * percentage)
    print (f"[INFO] readjust... target size: {target_width}x{target_height}")

print (f"[INFO] resizing {image.width}x{image.height} to {target_width}x{target_height}") 
    # resized_image = image.resize((target_width, target_height), resample=Image.Resampling.LANCZOS)
try:
    resized_image = image.resize((target_width, target_height), resample=Image.Resampling.NEAREST)
    resized_image.save('assets\\splash.bmp')
    print (f"[INFO] image resized successfully to {target_width}x{target_height}!")
except Exception as e:
    print (f"[ERROR] resizing image failed!") 
    self.error_occurred.emit(fp, str(e))
