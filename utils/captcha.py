import cv2
import pytesseract
import re

pattern = re.compile("[^A-Za-z0-9]")

def ocr(img_path):
    try:
        image = cv2.imread(img_path, 0)
        image = 255 - image
        ret, output = cv2.threshold(image, 128, 255, cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
        close = cv2.morphologyEx(output, cv2.MORPH_CLOSE, kernel, iterations=2)
        clean = cv2.fastNlMeansDenoising(close, h=50)
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
        dilate = cv2.dilate(clean, dilate_kernel, iterations=1)
        result = 255 - dilate 
        result = pytesseract.image_to_string(result).strip()
        return re.sub(pattern, '', result)
    except Exception as ex:
        print(ex)
        return ''
