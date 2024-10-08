import cv2
import pyautogui
import keyboard
import numpy as np
import time
import threading
import win32gui
import win32process
import psutil
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPainter, QColor, QPen
from queue import Queue, Empty as QueueEmpty
import os
import sys

def getResourcePath(relativePath):
    try:
        basePath = sys._MEIPASS
    except Exception:
        basePath = os.path.abspath(".")
    return os.path.join(basePath, relativePath)

class ScriptSignals(QObject):
    toggleScript = pyqtSignal(bool)
    updateOverlay = pyqtSignal(tuple)
    updateOverlayColor = pyqtSignal(QColor)

scriptSignals = ScriptSignals()

class OverlayDisplay(QWidget):
    def __init__(self, x, y, width, height):
        super().__init__()
        self.setGeometry(x, y, width, height)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.activeColor = QColor(255, 0, 0, 128)
        self.show()

    def updatePositionAndSize(self, x, y, width, height):
        self.setGeometry(x, y, width, height)

    def toggleActiveColor(self, isActive):
        self.activeColor = QColor(0, 255, 0, 128) if isActive else QColor(255, 0, 0, 128)
        self.update()

    def setColor(self, color):
        self.activeColor = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(self.activeColor, 2)
        painter.setPen(pen)
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)

currentRegion = None
isScriptActive = False
currentKeyHeld = None
keyQueue = Queue()
keyPositions = {'a': None, 's': None, 'd': None}
isCalibrated = False
stopExecution = threading.Event()

keyTemplates = {
    'a': cv2.imread(getResourcePath('a_template.png'), cv2.IMREAD_GRAYSCALE),
    's': cv2.imread(getResourcePath('s_template.png'), cv2.IMREAD_GRAYSCALE),
    'd': cv2.imread(getResourcePath('d_template.png'), cv2.IMREAD_GRAYSCALE),
    'held_a': cv2.imread(getResourcePath('held_a_template.png'), cv2.IMREAD_GRAYSCALE),
    'held_s': cv2.imread(getResourcePath('held_s_template.png'), cv2.IMREAD_GRAYSCALE),
    'held_d': cv2.imread(getResourcePath('held_d_template.png'), cv2.IMREAD_GRAYSCALE)
}

matchThreshold = 0.75

def findRobloxWindow():
    def enumWindowCallback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            if process.name() in ["RobloxPlayerBeta.exe", "Roblox.exe"]:
                hwnds.append(hwnd)
        return True

    hwnds = []
    win32gui.EnumWindows(enumWindowCallback, hwnds)
    return hwnds[0] if hwnds else None

def calculateRegion(windowHandle):
    if not windowHandle:
        return None
    left, top, right, bottom = win32gui.GetWindowRect(windowHandle)
    width, height = right - left, bottom - top
    centerX, centerY = left + width // 2, top + height // 2
    regionWidth, offsetY, reducedHeight = 200, 80, 80
    leftX = centerX - regionWidth // 2
    topY = centerY + offsetY - (regionWidth - reducedHeight) // 2
    return (leftX, topY, regionWidth, regionWidth - reducedHeight)

def detectCurrentKey():
    if not isCalibrated:
        return None

    screenshot = pyautogui.screenshot(region=currentRegion)
    grayImage = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    
    for key in ['a', 's', 'd']:
        resultForHeldKey = cv2.matchTemplate(grayImage, keyTemplates[f'held_{key}'], cv2.TM_CCOEFF_NORMED)
        _, heldMaxVal, _, _ = cv2.minMaxLoc(resultForHeldKey)
        
        if heldMaxVal > matchThreshold:
            return key
        
        resultForKey = cv2.matchTemplate(grayImage, keyTemplates[key], cv2.TM_CCOEFF_NORMED)
        _, maxVal, _, _ = cv2.minMaxLoc(resultForKey)
        
        if maxVal > matchThreshold:
            return key
    
    return None

def calibrateKeyPositions():
    print("Calibrating...")
    scriptSignals.updateOverlayColor.emit(QColor(128, 0, 128, 128))  # Purple
    
    while not all(position is not None for position in keyPositions.values()):
        screenshot = pyautogui.screenshot(region=currentRegion)
        grayImage = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

        for key in ['a', 's', 'd']:
            if keyPositions[key] is not None:
                continue

            resultForKey = cv2.matchTemplate(grayImage, keyTemplates[key], cv2.TM_CCOEFF_NORMED)
            _, maxVal, _, maxLoc = cv2.minMaxLoc(resultForKey)
            
            if maxVal > matchThreshold:
                h, w = keyTemplates[key].shape
                centerX = maxLoc[0] + w // 2
                centerY = maxLoc[1] + h // 2
                
                if 0 <= centerX < currentRegion[2] and 0 <= centerY < currentRegion[3]:
                    keyPositions[key] = (centerX + currentRegion[0], centerY + currentRegion[1])
                    print(f"Calibrated {key.upper()} at {keyPositions[key]}")

        time.sleep(0.5)

    print("Calibration complete.")
    global isCalibrated
    isCalibrated = True
    scriptSignals.updateOverlayColor.emit(QColor(0, 255, 0, 128))  # Green
    return True

def holdMouseForDuration():
    if isScriptActive:
        pyautogui.mouseDown()
        time.sleep(1)
        pyautogui.mouseUp()

def mouseClickLoop():
    lastKeyPressTime = time.time()
    keyWasDetected = False
    while not stopExecution.is_set():
        if isScriptActive:
            currentTime = time.time()
            if currentKeyHeld:
                keyboard.press(currentKeyHeld)
                pyautogui.click()
                lastKeyPressTime = currentTime
                keyWasDetected = True
                time.sleep(np.random.uniform(0.002, 0.008))
            else:
                if currentTime - lastKeyPressTime > 0.5 and keyWasDetected:
                    holdMouseForDuration()
                    keyWasDetected = False
        else:
            if currentKeyHeld:
                keyboard.release(currentKeyHeld)
            keyWasDetected = False
        time.sleep(0.001)

def keyDetectionLoop():
    while not stopExecution.is_set():
        if isScriptActive:
            if not isCalibrated:
                if calibrateKeyPositions():
                    print("Calibration complete. Starting key detection.")
                    toggleScriptExecution(True)
                else:
                    print("Calibration failed. Retrying in 5 seconds.")
                    time.sleep(5)
                    continue

            detectedKey = detectCurrentKey()
            keyQueue.put(detectedKey)

        time.sleep(0.01)

def manageKeyStates():
    global currentKeyHeld
    lastKeyChangeTime = time.time()
    noKeyDetectionTime = time.time()
    
    while not stopExecution.is_set():
        try:
            newKey = keyQueue.get(timeout=0.1)
            currentTime = time.time()
            
            if newKey is not None:
                noKeyDetectionTime = currentTime
                
                if newKey != currentKeyHeld:
                    if currentTime - lastKeyChangeTime > 0.2:
                        if currentKeyHeld:
                            keyboard.release(currentKeyHeld)
                        currentKeyHeld = newKey
                        keyboard.press(currentKeyHeld)
                        print(f"Holding '{currentKeyHeld.upper()}'.")
                        lastKeyChangeTime = currentTime
            else:
                if currentTime - noKeyDetectionTime > 0.5:
                    if currentKeyHeld:
                        keyboard.release('a')
                        keyboard.release('s')
                        keyboard.release('d')
                        keyboard.release(currentKeyHeld)
                        currentKeyHeld = None
                        print("Stopped holding any key.")
                        lastKeyChangeTime = currentTime
                        
        except QueueEmpty:
            pass
        except Exception as e:
            print(f"Error in manageKeyStates: {e}")
            time.sleep(1)

def toggleScriptExecution(active):
    global isScriptActive
    isScriptActive = active
    if not isScriptActive:
        if currentKeyHeld:
            keyboard.release(currentKeyHeld)
        scriptSignals.updateOverlayColor.emit(QColor(255, 0, 0, 128))  # Red
    else:
        scriptSignals.updateOverlayColor.emit(QColor(0, 255, 0, 128))  # Green

def updateDetectionArea():
    global currentRegion
    windowHandle = findRobloxWindow()
    if windowHandle:
        newRegion = calculateRegion(windowHandle)
        if newRegion != currentRegion:
            currentRegion = newRegion
            scriptSignals.updateOverlay.emit(newRegion)
    else:
        currentRegion = None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    def handleOverlayUpdate(region):
        overlay.updatePositionAndSize(*region)
    
    def handleColorUpdate(color):
        overlay.setColor(color)
    
    scriptSignals.updateOverlay.connect(handleOverlayUpdate)
    scriptSignals.updateOverlayColor.connect(handleColorUpdate)
    
    overlay = OverlayDisplay(0, 0, 200, 200)
    
    updateDetectionArea()

    keyStateManagerThread = threading.Thread(target=manageKeyStates, daemon=True)
    keyStateManagerThread.start()

    keyDetectionThread = threading.Thread(target=keyDetectionLoop, daemon=True)
    keyDetectionThread.start()

    clickLoopThread = threading.Thread(target=mouseClickLoop, daemon=True)
    clickLoopThread.start()

    timer = QTimer()
    timer.timeout.connect(updateDetectionArea)
    timer.start(1000)
    
    toggleScriptExecution(False)

    def handleKeyPress(event):
        if event.name == 'r':
            toggleScriptExecution(not isScriptActive)

    keyboard.on_press(handleKeyPress)

    sys.exit(app.exec_())
