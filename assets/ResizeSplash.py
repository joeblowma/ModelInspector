#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# returns non-zero on fail and 0 on success
# takes simple args to either resize and convert, or just convert an image:
#     in_file, out_file, max_width, max_height
#       example: py ResizeSplash.py somefile.bmp somefile.bmp 400 600
#     in_file, out_file
#       example: py ResizeSplash.py somefile.bmp somefile.jpg
# ---------------------------------------------------------------------------
# ideally the purpose this was created for was to take a bitmap input
# conserve 0xFF00FF alpha transparency used by the pysplash lib when downsizing
# then output a pyinstaller compatible png so it doesn't have to convert anything
#
# by default pyinstaller splash screen max size is (760, 480)
# ---------------------------------------------------------------------------
import sys

from PIL import Image

# if resize_splash('assets\\splash_base.bmp', 'assets\\splash.png'):
# return 0


def get_target_sz(target_aspect, cur_aspect, calc_aspect):
    percentage = float(target_aspect) / float(cur_aspect)
    return (int(float(calc_aspect) * percentage), target_aspect)


def calc_target_sz(cur_width, cur_height, max_width, max_height):
    target_width = cur_width
    target_height = cur_height

    # width tends to be bigger, calc based on scaling it first
    if(cur_width > max_width):
        target_height, target_width = get_target_sz(max_width, cur_width, cur_height)

    # now make sure calculated height fits, if not resize based on height
    if(target_height > max_height):
        target_width, target_height = get_target_sz(max_height, cur_height, cur_width)

    return (target_width, target_height)


def alter_image(inFilePath, outFilePath, max_width=0, max_height=0):
    image = Image.open(inFilePath)
    #check if we need to resize
    if max_width != 0 and max_height != 0:
        target_width, target_height = calc_target_sz(image.width, image.height, max_width, max_height)
        print (f"[INFO] resizing {image.width}x{image.height} to {target_width}x{target_height}")
        try:
            resized_image = image.resize((target_width, target_height), resample=Image.Resampling.NEAREST)
            print (f"[INFO] image {inFilePath} resized successfully to {target_width}x{target_height}")
            resized_image.save(outFilePath)
            print (f"[INFO] output image {outFilePath} saved")
        except Exception:
            print ("[ERROR] resizing image {inFilePath} failed!")
            return False
    else:
        image.save(outFilePath)
        return True
    return False


def main():
    ret_val = 0
    if len(sys.argv) == 3:
        if alter_image(sys.argv[1], sys.argv[2]):
            ret_val = 1
    elif len(sys.argv) == 5:
        try:
            if alter_image(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])):
                ret_val = 1
        except Exception:
            print ("[ERROR] invalid command line!")
            print (f"[ERROR] parsing 'python {sys.argv[0]} {sys.argv[1]} {sys.argv[2]} {sys.argv[3]} {sys.argv[4]}'")
    else:
        print ("[ERROR] invalid command line! Not enough args!")
        print (f"[INFO] Usage: python {sys.argv[0]} infile outfile maxwidth maxheight")

    return ret_val

if __name__ == "__main__":
    main()
