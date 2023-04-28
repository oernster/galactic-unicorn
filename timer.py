# Create a secrets.py with your Wifi details to be able to get the time
# when the Galactic Unicorn isn't connected to Thonny.
#
# secrets.py should contain:
# WIFI_SSID = "Your WiFi SSID"
# WIFI_PASSWORD = "Your WiFi password"
#
import _thread
import time
import math
import machine
from machine import Timer
import network
import ntptime
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN as DISPLAY


try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
    wifi_available = True
except ImportError:
    print("Create secrets.py with your WiFi credentials to get time from NTP")
    wifi_available = False

lock = _thread.allocate_lock()

# constants for controlling the background colour throughout the day
MIDDAY_HUE = 1.1
MIDNIGHT_HUE = 0.8
HUE_OFFSET = -0.1

MIDDAY_SATURATION = 1.0
MIDNIGHT_SATURATION = 1.0

MIDDAY_VALUE = 0.8
MIDNIGHT_VALUE = 0.3

# create galactic object and graphics surface for drawing
gu = GalacticUnicorn()
graphics = PicoGraphics(DISPLAY)

# create the rtc object
rtc = machine.RTC()

width = GalacticUnicorn.WIDTH
height = GalacticUnicorn.HEIGHT

# set up some pens to use later
WHITE = graphics.create_pen(255, 255, 255)
BLACK = graphics.create_pen(0, 0, 0)

@micropython.native  # noqa: F821
def from_hsv(h, s, v):
    i = math.floor(h * 6.0)
    f = h * 6.0 - i
    v *= 255.0
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)

    i = int(i) % 6
    if i == 0:
        return int(v), int(t), int(p)
    if i == 1:
        return int(q), int(v), int(p)
    if i == 2:
        return int(p), int(v), int(t)
    if i == 3:
        return int(p), int(q), int(v)
    if i == 4:
        return int(t), int(p), int(v)
    if i == 5:
        return int(v), int(p), int(q)

# function for drawing a gradient background
def gradient_background(start_hue, start_sat, start_val, end_hue, end_sat, end_val):
    half_width = width // 2
    for x in range(0, half_width):
        hue = ((end_hue - start_hue) * (x / half_width)) + start_hue
        sat = ((end_sat - start_sat) * (x / half_width)) + start_sat
        val = ((end_val - start_val) * (x / half_width)) + start_val
        colour = from_hsv(hue, sat, val)
        graphics.set_pen(graphics.create_pen(int(colour[0]), int(colour[1]), int(colour[2])))
        for y in range(0, height):
            graphics.pixel(x, y)
            graphics.pixel(width - x - 1, y)

    colour = from_hsv(end_hue, end_sat, end_val)
    graphics.set_pen(graphics.create_pen(int(colour[0]), int(colour[1]), int(colour[2])))
    for y in range(0, height):
        graphics.pixel(half_width, y)

# function for drawing outlined text
def outline_text(text, x, y):
    graphics.set_pen(BLACK)
    graphics.text(text, x - 1, y - 1, -1, 1)
    graphics.text(text, x, y - 1, -1, 1)
    graphics.text(text, x + 1, y - 1, -1, 1)
    graphics.text(text, x - 1, y, -1, 1)
    graphics.text(text, x + 1, y, -1, 1)
    graphics.text(text, x - 1, y + 1, -1, 1)
    graphics.text(text, x, y + 1, -1, 1)
    graphics.text(text, x + 1, y + 1, -1, 1)

    graphics.set_pen(WHITE)
    graphics.text(text, x, y, -1, 1)

def sync_timer():
    if not wifi_available:
        return

    # Start connection
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(pm=0xa11140)  # Turn WiFi power saving off for some slow APs
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    # Wait for connect success or failure
    max_wait = 100
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('waiting for connection...')
        time.sleep(0.2)
    
        redraw_display_if_reqd()
        gu.update(graphics)
    
    if max_wait > 0:
        print("Connected")

        try:
            ntptime.settime()
            print("Time set")
        except OSError:
            pass
    
    wlan.disconnect()
    wlan.active(False)

# NTP synchronizes the time to UTC, this allows you to adjust the displayed time
# by one hour increments from UTC by pressing the volume up/down buttons
#
# We use the IRQ method to detect the button presses to avoid incrementing/decrementing
# multiple times when the button is held.
utc_offset = 0

up_button = machine.Pin(GalacticUnicorn.SWITCH_VOLUME_UP, machine.Pin.IN, machine.Pin.PULL_UP)
down_button = machine.Pin(GalacticUnicorn.SWITCH_VOLUME_DOWN, machine.Pin.IN, machine.Pin.PULL_UP)

def adjust_utc_offset(pin):
    global utc_offset
    if pin == up_button:
        utc_offset += 1
    if pin == down_button:
        utc_offset -= 1

up_button.irq(trigger=machine.Pin.IRQ_FALLING, handler=adjust_utc_offset)
down_button.irq(trigger=machine.Pin.IRQ_FALLING, handler=adjust_utc_offset)

up_button = machine.Pin(GalacticUnicorn.SWITCH_VOLUME_UP, machine.Pin.IN, machine.Pin.PULL_UP)
down_button = machine.Pin(GalacticUnicorn.SWITCH_VOLUME_DOWN, machine.Pin.IN, machine.Pin.PULL_UP)

year_clock, month_clock, day_clock, wd_clock, hour_clock, minute_clock, second_clock, last_second = rtc.datetime()

tens = 0
second = 0
minute = 0
hour = 0
stored_tens = 0
stored_second = second
stored_minute = minute
stored_hour = hour
first = True
start = False
a_pressed = False
b_pressed = False
c_pressed = False
d_pressed = True


# Check whether the RTC time has changed and if so redraw the display
def redraw_display_if_reqd():
    global start, first, hour, minute, second, tens, stored_hour, stored_minute, stored_second, stored_tens, a_pressed, b_pressed, c_pressed, d_pressed
    if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_UP):
        gu.adjust_brightness(+0.01)
    elif gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_DOWN):
        gu.adjust_brightness(-0.01)
    elif gu.is_pressed(GalacticUnicorn.SWITCH_A):
        lock.acquire()
        tens = 0
        second = 0
        minute = 0
        hour = 0
        start = True
        a_pressed = True
        b_pressed = False
        c_pressed = False
        d_pressed = False
        lock.release()
    elif gu.is_pressed(GalacticUnicorn.SWITCH_B):
        lock.acquire()
        start = False
        stored_tens = tens
        stored_second = second
        stored_minute = minute
        stored_hour = hour
        a_pressed = False
        b_pressed = True
        c_pressed = False
        d_pressed = False
        lock.release()
    elif gu.is_pressed(GalacticUnicorn.SWITCH_C):
        lock.acquire()
        start = False
        a_pressed = False
        b_pressed = False
        c_pressed = True
        d_pressed = False
        lock.release()
    elif gu.is_pressed(GalacticUnicorn.SWITCH_D):
        lock.acquire()
        start = False
        a_pressed = False
        b_pressed = False
        c_pressed = False
        d_pressed = True
        lock.release()
    
    time.sleep(0.01)
        
    # update the display
    gu.update(graphics)
    
    lock.acquire()
        
    if a_pressed:
        if tens > 0 and tens % 10 == 0:
            second += 1
            tens = 0
        if second > 0 and second % 60 == 0:
            minute += 1
            second = 0
        if second > 0 and second % 60 == 0:
            hour += 1
            minute = 0
        if minute > 0 and minute % 60 == 0:
            hour += 1
            minute = 0
        timer = "{:02}:{:02}:{:02}:{:01}".format(hour, minute, second, tens)
        percent_to_midday = 50
        hue = ((MIDDAY_HUE - MIDNIGHT_HUE) * percent_to_midday) + MIDNIGHT_HUE
        sat = ((MIDDAY_SATURATION - MIDNIGHT_SATURATION) * percent_to_midday) + MIDNIGHT_SATURATION
        val = ((MIDDAY_VALUE - MIDNIGHT_VALUE) * percent_to_midday) + MIDNIGHT_VALUE

        gradient_background(hue, sat, val,
                            hue + HUE_OFFSET, sat, val)

        # calculate text position so that it is centred
        w = graphics.measure_text(timer, 1)
        x = int(width / 2 - w / 2 + 1)
        y = 2

        outline_text(timer, x, y)
        if start:
            tens += 1
    elif b_pressed:
        timer = "{:02}:{:02}:{:02}:{:01}".format(hour, minute, second, tens)
        percent_to_midday = 50
        hue = ((MIDDAY_HUE - MIDNIGHT_HUE) * percent_to_midday) + MIDNIGHT_HUE
        sat = ((MIDDAY_SATURATION - MIDNIGHT_SATURATION) * percent_to_midday) + MIDNIGHT_SATURATION
        val = ((MIDDAY_VALUE - MIDNIGHT_VALUE) * percent_to_midday) + MIDNIGHT_VALUE

        gradient_background(hue, sat, val,
                            hue + HUE_OFFSET, sat, val)

        # calculate text position so that it is centred
        w = graphics.measure_text(timer, 1)
        x = int(width / 2 - w / 2 + 1)
        y = 2

        outline_text(timer, x, y)
    elif c_pressed:
        timer = "{:02}:{:02}:{:02}:{:01}".format(stored_hour, stored_minute, stored_second, stored_tens)
        percent_to_midday = 50
        hue = ((MIDDAY_HUE - MIDNIGHT_HUE) * percent_to_midday) + MIDNIGHT_HUE
        sat = ((MIDDAY_SATURATION - MIDNIGHT_SATURATION) * percent_to_midday) + MIDNIGHT_SATURATION
        val = ((MIDDAY_VALUE - MIDNIGHT_VALUE) * percent_to_midday) + MIDNIGHT_VALUE

        gradient_background(hue, sat, val,
                            hue + HUE_OFFSET, sat, val)

        # calculate text position so that it is centred
        w = graphics.measure_text(timer, 1)
        x = int(width / 2 - w / 2 + 1)
        y = 2

        outline_text(timer, x, y)
        
    elif d_pressed or first:
        first = False
        global year_clock, month_clock, day_clock, wd_clock, hour_clock, minute_clock, second_clock, last_second

        year_clock, month_clock, day_clock, wd_clock, hour_clock, minute_clock, second_clock, _ = rtc.datetime()
        if second_clock != last_second:
            hour_clock = (hour_clock + utc_offset) % 24
            time_through_day = (((hour_clock * 60) + minute_clock) * 60) + second_clock
            percent_through_day = time_through_day / 86400
            percent_to_midday = 1.0 - ((math.cos(percent_through_day * math.pi * 2) + 1) / 2)

            hue = ((MIDDAY_HUE - MIDNIGHT_HUE) * percent_to_midday) + MIDNIGHT_HUE
            sat = ((MIDDAY_SATURATION - MIDNIGHT_SATURATION) * percent_to_midday) + MIDNIGHT_SATURATION
            val = ((MIDDAY_VALUE - MIDNIGHT_VALUE) * percent_to_midday) + MIDNIGHT_VALUE

            gradient_background(hue, sat, val,
                                hue + HUE_OFFSET, sat, val)

            clock = "{:02}:{:02}:{:02}".format(hour_clock, minute_clock, second_clock)

            # calculate text position so that it is centred
            w = graphics.measure_text(clock, 1)
            x = int(width / 2 - w / 2 + 1)
            y = 2

            outline_text(clock, x, y)

            last_second = second
    lock.release()
# set the font
graphics.set_font("bitmap8")
gu.set_brightness(0.5)

sync_timer()

def interruption_handler(timer):
    redraw_display_if_reqd()

soft_timer = Timer(mode=Timer.PERIODIC, period=100, callback=interruption_handler)        

def console_handler():
    global start, hour, minute, second, tens, stored_hour, stored_minute, stored_second, stored_tens, a_pressed, b_pressed, c_pressed, d_pressed
    print("Command options...")
    print("A) Start timer.")
    print("B) Stop timer.")
    print("C) Recall last stopped timer.")
    print("D) Display real time clock.")
    print("R) Reset timer to zero.")
    ci = input("Enter a command:")
    lock.acquire()
    if ci.lower() == 'a':
        tens = 0
        second = 0
        minute = 0
        hour = 0
        start = True
        a_pressed = True
        b_pressed = False
        c_pressed = False
        d_pressed = False
    elif ci.lower() == 'b':
        start = False
        stored_tens = tens
        stored_second = second
        stored_minute = minute
        stored_hour = hour
        a_pressed = False
        b_pressed = True
        c_pressed = False
        d_pressed = False
    elif ci.lower() == 'c':
        start = False
        a_pressed = False
        b_pressed = False
        c_pressed = True
        d_pressed = False
    elif ci.lower() == 'd':
        start = False
        a_pressed = False
        b_pressed = False
        c_pressed = False
        d_pressed = True
    elif ci.lower() == 'r':
        tens = 0
        second = 0
        minute = 0
        hour = 0
        start = False
        a_pressed = True
        b_pressed = False
        c_pressed = False
        d_pressed = False
    else:
        print("Invalid command!")
    lock.release()
    time.sleep(0.01)

while True:
    console_handler()
