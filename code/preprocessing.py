import cv2
import numpy as np


# FUNCTIONS FOR IMAGE PREPROCESSING

def grayscale(img):
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def noise_removal(img):
    kernel = np.ones((3, 3), np.uint8)

    # img = cv2.dilate(img, kernel2, iterations=1)
    # img = cv2.erode(img, kernel3, iterations=1)

    img = cv2.medianBlur(img, 3)
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)

    return img


def otsu_threshold(img):
    # otsu automatically picks the best global threshold value
    threshold_used, result = cv2.threshold(
        img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return result


def adaptive_threshold(img):
    # threshold is calculated per region instead of globally
    return cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        1701,  # block size, size of the neighborhood used to calculate threshold for each pixel (must be odd)
        65  # constant subtracted from the mean/weighted mean, fine-tunes sensitivity
    )