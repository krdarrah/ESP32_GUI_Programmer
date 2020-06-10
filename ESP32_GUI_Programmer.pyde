#ESP32 Programmer
#processing python mode
#only need controlP5 library

# THIS IS COPIED FROM espota.py
# Original espota.py by Ivan Grokhotkov:
# https://gist.github.com/igrr/d35ab8446922179dc58c
#
# Modified since 2015-09-18 from Pascal Gollor (https://github.com/pgollor)
# Modified since 2015-11-09 from Hristo Gochkov (https://github.com/me-no-dev)
# Modified since 2016-01-03 from Matthew O'Gorman (https://githumb.com/mogorman)
#
# This script will push an OTA update to the ESP
# use it like: python espota.py -i <ESP_IP_address> -I <Host_IP_address> -p <ESP_port> -P <Host_port> [-a password] -f <sketch.bin>
# Or to upload SPIFFS image:
# python espota.py -i <ESP_IP_address> -I <Host_IP_address> -p <ESP_port> -P <HOST_port> [-a password] -s -f <spiffs.bin>
#
# Changes
# 2015-09-18:
# - Add option parser.
# - Add logging.
# - Send command to controller to differ between flashing and transmitting SPIFFS image.
#
# Changes
# 2015-11-09:
# - Added digest authentication
# - Enhanced error tracking and reporting
#
# Changes
# 2016-01-03:
# - Added more options to parser.
#
from __future__ import print_function
import socket
import sys
import os
import optparse
import logging
import hashlib
import random

# Commands
FLASH = 0
SPIFFS = 100
AUTH = 200
PROGRESS = True
TIMEOUT = 10
OTAstatus = "waiting for file..."# used for updating GUI status
# Accepts a float between 0 and 1. Any int will be converted to a float.
# A value under 0 represents a 'halt'.
# A value at 1 or bigger represents 100%
def update_progress(progress):
    if (PROGRESS):
        barLength = 20  # Modify this to change the length of the progress bar
        status = ""
        if isinstance(progress, int):
            progress = float(progress)
        if not isinstance(progress, float):
            progress = 0
            status = "error: progress var must be float\r\n"
        if progress < 0:
            progress = 0
            status = "Halt...\r\n"
        if progress >= 1:
            progress = 1
            status = "Done...\r\n"
        block = int(round(barLength * progress))
        msg = "\rUploading: [{0}] {1}% {2}".format(
            "=" * block + " " * (barLength - block), int(progress * 100), status)
        sys.stderr.write(msg)
        sys.stderr.flush()
        global OTAstatus
        OTAstatus = msg
        
    else:
        sys.stderr.write('.')
        sys.stderr.flush()# Accepts a float between 0 and 1. Any int will be converted to a float.


def serve(remoteAddr, localAddr, remotePort, localPort, password, filename, command=FLASH):
    global OTAstatus
    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = (localAddr, localPort)
    logging.info('Starting on %s:%s', str(
        server_address[0]), str(server_address[1]))
    OTAstatus = "Starting"
    try:
        sock.bind(server_address)
        sock.listen(1)
        OTAstatus = "Binding"
    except:
        logging.error("Listen Failed")
        OTAstatus = "Listen Failed"
        return 1

    content_size = os.path.getsize(filename)
    f = open(filename, 'rb')
    file_md5 = hashlib.md5(f.read()).hexdigest()
    f.close()
    OTAstatus = "Sending Command"
    logging.info('Upload size: %d', content_size)
    message = '%d %d %d %s\n' % (command, localPort, content_size, file_md5)

    # Wait for a connection
    inv_trys = 0
    data = ''
    
    msg = 'Sending invitation to %s ' % (remoteAddr)
    OTAstatus = msg

    sys.stderr.write(msg)
    sys.stderr.flush()
    #return 0
    while (inv_trys < 10):
        inv_trys += 1
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        remote_address = (remoteAddr, int(remotePort))
        try:
            sent = sock2.sendto(message.encode(), remote_address)
        except:
            OTAstatus = "Failed Host Not found"
            sys.stderr.write('failed\n')
            sys.stderr.flush()
            sock2.close()
            logging.error('Host %s Not Found', remoteAddr)
            return 1
        sock2.settimeout(TIMEOUT)
        try:
            data = sock2.recv(37).decode()
            break
        except:
            sys.stderr.write('.')
            sys.stderr.flush()
            sock2.close()
    sys.stderr.write('\n')
    sys.stderr.flush()
    if (inv_trys == 10):
        logging.error('No response from the ESP')
        OTAstatus = "No response"
        return 1
    if (data != "OK"):
        if(data.startswith('AUTH')):
            nonce = data.split()[1]
            cnonce_text = '%s%u%s%s' % (
                filename, content_size, file_md5, remoteAddr)
            cnonce = hashlib.md5(cnonce_text.encode()).hexdigest()
            passmd5 = hashlib.md5(password.encode()).hexdigest()
            result_text = '%s:%s:%s' % (passmd5, nonce, cnonce)
            result = hashlib.md5(result_text.encode()).hexdigest()
            sys.stderr.write('Authenticating...')
            sys.stderr.flush()
            message = '%d %s %s\n' % (AUTH, cnonce, result)
            sock2.sendto(message.encode(), remote_address)
            sock2.settimeout(10)
            try:
                data = sock2.recv(32).decode()
            except:
                sys.stderr.write('FAIL\n')
                logging.error('No Answer to our Authentication')
                sock2.close()
                return 1
            if (data != "OK"):
                sys.stderr.write('FAIL\n')
                logging.error('%s', data)
                sock2.close()
                sys.exit(1)
                return 1
            sys.stderr.write('OK\n')
        else:
            logging.error('Bad Answer: %s', data)
            sock2.close()
            return 1
    sock2.close()

    logging.info('Waiting for device...')
    OTAstatus = "Waiting"
    try:
        sock.settimeout(10)
        connection, client_address = sock.accept()
        sock.settimeout(None)
        connection.settimeout(None)
    except:
        OTAstatus = "No response"
        logging.error('No response from device')
        sock.close()
        return 1
    try:
        f = open(filename, "rb")
        if (PROGRESS):
            update_progress(0)
        else:
            OTAstatus = "Uploading"
            sys.stderr.write('Uploading')
            sys.stderr.flush()
        offset = 0
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            offset += len(chunk)
            update_progress(offset / float(content_size))
            connection.settimeout(10)
        
            try:
                connection.sendall(chunk)
                res = connection.recv(10)
                lastResponseContainedOK = 'OK' in res.decode()
            except:
                OTAstatus = "Error Uploading"
                sys.stderr.write('\n')
                logging.error('Error Uploading')
                connection.close()
                f.close()
                sock.close()
                return 1

        if lastResponseContainedOK:
            OTAstatus = "Success"
            logging.info('Success')
            connection.close()
            f.close()
            sock.close()
            return 0

        sys.stderr.write('\n')
        logging.info('Waiting for result...')
        OTAstatus = "Waiting for result"
        try:
            count = 0
            while True:
                count = count + 1
                connection.settimeout(60)
                data = connection.recv(32).decode()
                logging.info('Result: %s', data)

                if "OK" in data:
                    OTAstatus = "Success"
                    logging.info('Success')
                    connection.close()
                    f.close()
                    sock.close()
                    return 0
                if count == 5:
                    OTAstatus = "Error response"
                    logging.error('Error response from device')
                    connection.close()
                    f.close()
                    sock.close()
                    return 1
        except e:
            OTAstatus = "No Result"
            logging.error('No Result!')
            connection.close()
            f.close()
            sock.close()
            return 1

    finally:
        connection.close()
        f.close()

    sock.close()
    return 1
# end serve

# GUI LIBRARY
# * by Andreas Schlegel, 2012
# * www.sojamo.de/libraries/controlp5
# https://github.com/sojamo/controlp5
add_library('controlP5')

fileToUpload = ""
ipAddressText = "192.168.1.100"#default ip address



def setup():
    
    size(480, 120)
    selectInput("Select a bin file to upload:", "fileSelected")
    font20 = createFont("sansserif", 20)
    font14 = createFont("sansserif", 14)
    
    #GUI SETUP
    global cp5
    cp5 = ControlP5(this)
    
    #INPUT IP ADDRESS TEXT FIELD
    cp5.addTextfield("inputIP")\
    .setPosition(20, 50)\
    .setSize(175, 40)\
    .setFont(font20)\
    .setFocus(True)\
    .setColor(color(0))\
    .setColorBackground(color(255))\
    .setColorCursor(color(0))\
    .setText(ipAddressText)\
    .setAutoClear(False)\
    .setLabel("esp32 ip address")\
    .setColorLabel(color(0))\
    
    
    #UPLOAD BUTTON
    cp5.addButton("Upload")\
    .setPosition(210, 50)\
    .setSize(100, 40)\
    .setFont(font20)\
    
    textFont(font14);
    

def draw():
    background(255)
    fill(0)
    text(OTAstatus,10,20)

def mouseClicked():
    if (cp5.get(Button, "Upload").isOn()):
        thread("runServer")

def runServer():
    myPort = random.randint(10000,60000)
    global ipAddressText
    ipAddressText = cp5.get(Textfield, "inputIP").getText()
    serve(ipAddressText, "0.0.0.0", 3232, myPort, "",fileToUpload, FLASH)

def fileSelected(selection):
    if selection == None:
        print("Window was closed or the user hit cancel.")
        exit()
    else:
        global fileToUpload
        global OTAstatus
        fileToUpload = ("%s" % (selection.getAbsolutePath()))
        OTAstatus = "File to Upload: " + selection.getName()
   
