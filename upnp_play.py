import requests
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time
import lxml.etree as etree
import socket
import netifaces as ni
import shutil
import os
import random
from urllib.parse import urlparse
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
import mimetypes
import configparser
import re
import sys
import ast

# --- Read configuration from config.ini
config = configparser.ConfigParser()
config.read('./config.ini')
default_section = config['DEFAULT']

SERVER_PORT = None  # Initialize to None for error checking
threshold = None
order_files = None
directory_path = None

try:
    SERVER_PORT = default_section.getint('SERVER_PORT')
except ValueError:
    print("Error: SERVER_PORT must be an integer in config file.")
    # Handle the error: use a default, exit, etc.
    SERVER_PORT = 8080 # Example default

try:
    threshold = default_section.getint('threshold')
except ValueError:
    print("Error: threshold must be an integer in config file.")
    threshold = 100 # Example default

try:
    order_files_str = default_section['order_files']  # Read as string first
    print(f"order_files_str: {order_files_str}")
    order_files = ast.literal_eval(order_files_str) 
    print(f"order_files: {order_files}")
except KeyError:
    print("Error: order_files is missing in config file.")
    order_files = False  # Default
except ValueError: # this will never be raised now, but can be useful to catch other errors
    print("Error: order_files must be a boolean (true/false/1/0/yes/no) in config file.")
    order_files = False  # Default

try:
    directory_path = default_section['directory_path']
except KeyError:
    print("Error: directory_path is missing in config file.")
    directory_path = "./music"  # Example default


# Check if all required variables were successfully loaded
if SERVER_PORT is None or threshold is None or order_files is None or directory_path is None:
    print("Error: Some required configuration values could not be loaded.")
    exit(1)  # Or handle it differently

print(SERVER_PORT, threshold, order_files, directory_path) # Test/verify


# --- UPNP SSDP protocol
def discover_devices():
    """Discovers UPnP Media Renderers on the network, preventing duplicates and handling errors."""
    multicast_address = '239.255.255.250'
    multicast_port = 1900

    message = b'M-SEARCH * HTTP/1.1\r\n' \
              b'HOST: 239.255.255.250:1900\r\n' \
              b'MAN: "ssdp:discover"\r\n' \
              b'MX: 3\r\n' \
              b'ST: ssdp:all\r\n\r\n'

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(5)
        sock.sendto(message, (multicast_address, multicast_port))
    except socket.error as e:
        print(f"Error creating or sending socket: {e}")
        return []  # Return empty list on error

    location_server_pairs_set = set()

    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                response = data.decode()
                location_server = extract_location_server(response)
                if location_server:
                    if location_server not in location_server_pairs_set: # Check before adding!
                      location_server_pairs_set.add(location_server)
                      #print(f"Location: {location_server[0]}")
                      #print(f"Server: {location_server[1]}")
            except socket.timeout:
                #print("No responses received or no responses containing the specified tag.")
                print(" ")
                break # Exit the loop when timeout occurs
            except UnicodeDecodeError:
                print("Error decoding response. Skipping.") # Handle decoding errors
            except Exception as e:
                print(f"An unexpected error occurred: {e}") # Handle general exceptions

    finally:
        if 'sock' in locals(): # Check if socket was created before closing
            sock.close()

    return list(location_server_pairs_set)


def extract_location_server(response):
    """Extracts Location and Server information from a UPnP response, handling potential errors."""
    try:
        lines = response.splitlines()
        media_renderer_index = -1
        for i, line in enumerate(lines):
            if "urn:schemas-upnp-org:device:MediaRenderer" in line:
                media_renderer_index = i
                break

        if media_renderer_index != -1:
            start_index = max(0, media_renderer_index - 7)
            end_index = min(len(lines) - 1, media_renderer_index + 1)

            lines_to_save = lines[start_index:end_index + 4]

            location = None
            server = None

            for line in lines_to_save:
                if line.upper().startswith("LOCATION:"):
                    location = line.split(":", 1)[1].strip()
                if line.upper().startswith("SERVER:"):
                    server = line.split(":", 1)[1].strip()

            if location and server:
                return (location, server)
        return None # Explicitly return None if no match is found or errors occur

    except Exception as e:
        print(f"Error extracting Location/Server: {e}")
        return None  # Return None on error


def get_control_url(location):
    """Retrieves the Control URL for the AVTransport service from a device's description XML."""
    try:
        response = requests.get(location)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        root = ET.fromstring(response.text)
        namespaces = {'xmlns': 'urn:schemas-upnp-org:device-1-0'}

        service_type = "urn:schemas-upnp-org:service:AVTransport:1"
        control_url = None

        for service in root.findall('.//xmlns:service', namespaces):
            type_element = service.find('xmlns:serviceType', namespaces)
            if type_element is not None and type_element.text == service_type:
                control_url_element = service.find('xmlns:controlURL', namespaces)
                if control_url_element is not None:
                    control_url = control_url_element.text
                    break

        return control_url

    except requests.exceptions.RequestException as e:
        print(f"Error during request to {location}: {e}")
        return None
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return None
    except Exception as e:
        print(f"Other error during XML processing: {e}")
        return None



def process_device(location, server):
    """Processes a selected device, retrieving the Control URL and printing information."""
    control_url = get_control_url(location)

    if control_url:
        print(f"Control URL for AVTransport: {control_url}")

        parsed_url = urlparse(location)
        host = parsed_url.hostname
        port = parsed_url.port if parsed_url.port else 80
        host_port = f"{host}:{port}"
        print(f"Host and port from LOCATION: {host_port}")

        full_url = f"http://{host_port}{control_url}"
        return full_url
        print(f"Full URL: {full_url}")
    else:
        print(f"AVTransport service not found or error retrieving XML for {server}.")


def orchestrate_ssdp():
    """Main function to orchestrate device discovery and processing."""
    location_server_pairs = discover_devices()

    if location_server_pairs:
        print("\nServer UPNP/DLNA Selection Menu:")
        for i, (location, server) in enumerate(location_server_pairs):
            print(f"{i + 1}. {server}")

        print("0. Exit")

        while True:
            try:
                choice = int(input("Select an option: "))

                if choice == 0:
                    return  # Exit the function

                elif 1 <= choice <= len(location_server_pairs):
                    location_selected = location_server_pairs[choice - 1][0]
                    server_selected = location_server_pairs[choice - 1][1]
                    print(f"Location corresponding to {server_selected}: {location_selected}")
                    CONTROL_URL=process_device(location_selected, server_selected)
                    print(f"CONTROL_URL: {CONTROL_URL}")
                    return CONTROL_URL
                    break  # Exit the loop after a valid selection

                else:
                    print("Invalid choice. Please try again.")

            except ValueError:
                print("Invalid input. Please enter a number.")
    else:
        print("No devices found.")
        sys.exit(0)  # 0 indicates successful exit




# --- Returns the local IP address of the machine.
def get_local_ip():
    for interface in ni.interfaces():
        addresses = ni.ifaddresses(interface)
        if socket.AF_INET in addresses:
            for ip_address in addresses[socket.AF_INET]:
                if ip_address['addr'].startswith('192.168') or ip_address['addr'].startswith('10.'):
                    return ip_address['addr']
    return None

ip_address = get_local_ip()
print(f"The local IP address is: {ip_address}")


def copy_file(source_file, destination_file):
    """
    Copies a file from a source path to a destination path.

    Args:
        source_file: The path of the file to be copied.
        destination_file: The path where the file should be copied.
    """
    try:
        shutil.copy2(source_file, destination_file)
        print(f"The file '{source_file}' has been copied to '{destination_file}'")
    except FileNotFoundError:
        print(f"Error: the file '{source_file}' was not found.")
    except Exception as e:
        print(f"An error occurred during the copy: {e}")


# --- Funzioni ---
def send_upnp_request(soap_action, xml_data):
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': f'"{soap_action}"',
    }
    try:
        response = requests.post(CONTROL_URL, headers=headers, data=xml_data)
        response.raise_for_status() # Throws an exception for invalid HTTP status codes (4xx or 5xx)
        print(f"Request for {soap_action}")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error in request for {soap_action}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error while requesting for {soap_action}: {e}")
        return None

def parse_xml_response(xml_string, namespaces=None):
    try:
        xml_bytes = xml_string.encode('utf-8')  # Encode the string into bytes
        root = etree.fromstring(xml_bytes) # Use lxml here
        return root, None
    except etree.XMLSyntaxError as e:  # Handle lxml exception
        print(f"Error parsing XML: {e}")
        print(xml_string)
        return None, e
    except Exception as e:
        print(f"Unexpected error while parsing XML: {e}")
        print(xml_string)
        return None, e


# --- Web Server ---
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import mimetypes
import socket

class MyHandler(BaseHTTPRequestHandler):
    def handle_connection_error(self, e):
        """Silently handle connection errors without trying to send error responses"""
        if isinstance(e, (BrokenPipeError, ConnectionResetError)):
            # Suppress the error trace for client disconnections
            self.close_connection = True
            return True
        return False

    def do_GET(self):
        try:
            filename = self.path[1:]
            if not filename:
                self.send_error(404, "File not specified")
                return
                
            file_path = filename
            if not os.path.exists(file_path):
                self.send_error(404, "File not found")
                return

            try:
                with open(file_path, "rb") as f:
                    self.send_response(200)
                    # Determine the Content-type based on the file extension
                    content_type, _ = mimetypes.guess_type(file_path)
                    if content_type is None:
                        content_type = 'application/octet-stream'
                    self.send_header('Content-type', content_type)
                    self.end_headers()
                    
                    chunk_size = 1024 * 64
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError) as e:
                            # Client disconnected - stop sending data
                            self.handle_connection_error(e)
                            return
                        
            except Exception as e:
                if not self.handle_connection_error(e):
                    self.send_error(500, f"Error serving file: {str(e)}")
                    
        except Exception as e:
            if not self.handle_connection_error(e):
                self.send_error(500, f"Internal server error: {str(e)}")

    def do_HEAD(self):
        try:
            filename = self.path[1:]
            if not filename:
                self.send_error(404, "File not specified")
                return
                
            file_path = filename
            if os.path.exists(file_path):
                self.send_response(200)
                content_type, _ = mimetypes.guess_type(file_path)
                if content_type is None:
                    content_type = 'application/octet-stream'
                self.send_header('Content-type', content_type)
                self.end_headers()
            else:
                self.send_error(404, "File not found")
                
        except Exception as e:
            if not self.handle_connection_error(e):
                self.send_error(500, "Internal server error")

def run_web_server(port):
    server_address = ('', port)
    httpd = HTTPServer(server_address, MyHandler)
    print(f"Web server running on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Server shutdown...")
        httpd.server_close()
    except Exception as e:
        print(f"Critical Server Error: {e}")
        httpd.server_close()

# --- Play ---
play_xml = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
      <InstanceID>0</InstanceID>
      <Speed>1</Speed>
    </u:Play>
  </s:Body>
</s:Envelope>"""

# --- Stop ---
stop_xml = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
      <InstanceID>0</InstanceID>
    </u:Stop>
  </s:Body>
</s:Envelope>"""

# --- PositionInfo ---
PositionInfo_xml = """<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:GetPositionInfo></s:Body></s:Envelope>"""

# --- GetTransportInfo Loop ---
def get_transport_info_loop():
    proc_running = True  # Internal control variable
    while proc_running:
        get_transport_info_xml = """<?xml version="1.0"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
              <InstanceID>0</InstanceID>
            </u:GetTransportInfo>
          </s:Body>
        </s:Envelope>"""

        transport_info_response = send_upnp_request("urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo", get_transport_info_xml)

        if transport_info_response:
            print("GetTransportInfo request sent and response received. Parsing...")
            namespaces = {'s': 'http://schemas.xmlsoap.org/soap/envelope/', 'u': 'urn:schemas-upnp-org:service:AVTransport:1'}
            root, error = parse_xml_response(transport_info_response, namespaces)
            print(f"root: {root}")

            if root is not None:
                try:
                    transport_state = root.find('.//CurrentTransportState', namespaces=namespaces).text
                    print(f"Transport status: {transport_state}")

                    if transport_state == "STOPPED":
                        print("Player is STOPPED. Exiting loop.")
                        proc_running = False
                        break

                    transport_status = root.find('.//CurrentTransportStatus', namespaces=namespaces).text if root.find('.//CurrentTransportStatus', namespaces=namespaces) is not None else "N/A"
                    print(f"Specific state: {transport_status}")


                except AttributeError as e:
                    print(f"Errore durante la ricerca dell'elemento XML: {e}")
                    print(transport_info_response)
            else:
                print(f"Error finding XML element: {error}")
        else:
            print("GetTransportInfo request failed.")
            proc_running = False
            break           

        time.sleep(10)

def extract_number_from_filename(filename):
    """
    Extracts the number from a filename, handling different variations.
    """
    match = re.match(r"^(\d*)(\D*)", filename)  # Modified to handle numbers without leading zeros
    if match:
        number_str = match.group(1)
        if number_str:
            return int(number_str)  # Directly converts to integer
        else:
            return 0  # Handles the case of "file" without a number
    else:
        return None  # Handles invalid filenames


def filter_files_by_number(directory, threshold, order_files):
    """Filters files in a directory based on a number in their name.

    Args:
        directory: The path to the directory.
        threshold: The minimum number that the file number must be.
        order_files: A boolean value indicating whether to order the files.

    Returns:
        A list of filenames that meet the criteria.
    """

    # Check that the directory exists
    if not os.path.isdir(directory):
        print(f"The directory {directory} does not exist.")
        return []  # Return an empty list if the directory does not exist

    # List to store the files that meet the criteria
    filtered_files = []

    # Iterate through all the files in the directory
    for filename in os.listdir(directory):
        # Check if the file has extension .mp3 or .flac
        if filename.endswith('.mp3') or filename.endswith('.flac'):
            try:
                # Extract the first three characters and convert them to a number
                file_number = extract_number_from_filename(filename)
                # Add the file to the list if the number is greater than the threshold
                if file_number >= threshold:
                    filtered_files.append((file_number, filename))
            except ValueError:
                # Ignore files that do not start with a valid number
                print(f"Error file ignored: {filename}")
                continue

    # Sort or shuffle the files based on the order_files variable
    if order_files:
        sorted_files = sorted(filtered_files)
    else:
        random.shuffle(filtered_files)
        sorted_files = filtered_files

    # Extract only the filenames from the list of tuples
    sorted_files_names = [filename for _, filename in sorted_files]

    return sorted_files_names  # Return the list of filenames

def replace_special_characters(text):
  """
  Replaces specific special characters in a string with predefined values.

  Args:
    text: The string to perform replacements on.

  Returns:
    The string with the characters replaced.
  """
  replacements = {
        "&": "e",
        "｜": "-",
        "⧸" : "-",
        "♫" : "-",
        "è": "e",
        "é": "e",  # e acute
        "ê": "e",  # e circumflex
        "ë": "e",  # e diaeresis/umlaut
        "à": "a",  # a grave
        "á": "a",  # a acute
        "â": "a",  # a circumflex
        "ä": "a",  # a diaeresis/umlaut
        "ì": "i",  # i grave
        "í": "i",  # i acute
        "î": "i",  # i circumflex
        "ï": "i",  # i diaeresis/umlaut
        "ò": "o",  # o grave
        "ó": "o",  # o acute
        "ô": "o",  # o circumflex
        "ö": "o",  # o diaeresis/umlaut
        "ù": "u",  # u grave
        "ú": "u",  # u acute
        "û": "u",  # u circumflex
        "ü": "u",  # u diaeresis/umlaut
        "ç": "c",  # c cedilla
        "ñ": "n",  # n tilde
        "’": " ",  # apostrophe (curly)
        "´": " ",  # acute accent (standalone)
        "'": " ",   # apostrophe (straight)
        "“": " ",   # double quotes (left)
        "”": " ",   # double quotes (right)
        "‘": " ",   # single quote (left)
        "’": " ",  # single quote (right) (already present)
        "—": "-",   # em dash
        "–": "-",   # en dash
        "…": "...", # horizontal ellipsis
  }
  for old_char, new_char in replacements.items():
    text = text.replace(old_char, new_char)
  return text


# Run the filter and get the list of files
filtered_file_list = filter_files_by_number(directory_path, threshold, order_files)

# --- run web server ---
web_server_thread = threading.Thread(target=run_web_server, args=(SERVER_PORT,))
web_server_thread.daemon = True
web_server_thread.start()
time.sleep(1)

CONTROL_URL=orchestrate_ssdp()
# Play mp3 to upnp device
FILE_PATH_ICON = "http://" + ip_address + ":" + str(SERVER_PORT) + "/icons8-python-100.png"
for filename in filtered_file_list:
    print(filename)
    # --- Remove &
    filename_view=filename
    filename_view=replace_special_characters(filename_view)
    print(filename_view)   
    if filename.endswith('.mp3'): 
        audio = MP3(directory_path + "/" + filename)
        filetocopy = "file.mp3"
    elif filename.endswith('.flac'):
        audio = FLAC(directory_path + "/" + filename) 
        filetocopy = "file.flac"   
    FILE_PATH = "http://" + ip_address + ":" + str(SERVER_PORT) + "/" + filetocopy   
    artist = audio.get('TPE1') # Artist
    if artist:
          artist = replace_special_characters(artist[0])
    else:  
          artist ="Python Script"
    print(f"artist: {artist}")
    album = audio.get('TALB')  # Album
    if album:
          album = replace_special_characters(album[0])
    else:  
          album ="Python Script"
    print(f"album: {album}")


    # --- SetAVTransportURI non compatible---
    set_uri_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
      <InstanceID>0</InstanceID>
      <CurrentURI>{FILE_PATH}</CurrentURI>
      <CurrentURIMetaData>
        &lt;DIDL-Lite xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot; xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot; xmlns:dlna=&quot;urn:schemas-dlna-org:metadata-1-0/&quot;&gt;
          &lt;item id=&quot;1&quot; parentID=&quot;1&quot; restricted=&quot;1&quot;&gt;
            &lt;upnp:class&gt;object.item.audioItem.audioBroadcast&lt;/upnp:class&gt;
            &lt;upnp:album&gt;{album}&lt;/upnp:album&gt;
            &lt;upnp:artist&gt;{artist}&lt;/upnp:artist&gt;
            &lt;upnp:albumArtURI&gt;{FILE_PATH_ICON}&lt;/upnp:albumArtURI&gt;
            &lt;dc:title&gt;{filename_view}&lt;/dc:title&gt;
            &lt;res protocolInfo=&quot;http-get:*:audio/mpeg:*&quot; &gt;{FILE_PATH} &lt;/res&gt;
          &lt;/item&gt;
        &lt;/DIDL-Lite&gt;
      </CurrentURIMetaData>
    </u:SetAVTransportURI>
  </s:Body>
</s:Envelope>"""

    # --- SetAVTransportURI compatible with Kodi ---
    set_uri_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
      <InstanceID>0</InstanceID>
      <CurrentURI>{FILE_PATH}</CurrentURI>
      <CurrentURIMetaData>
        &lt;DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:sec="http://www.sec.co.kr/" xmlns:pv="http://www.pv.com/pvns/" xmlns:dlna="urn:schemas-dlna-org:metadata-1-0"&gt;
          &lt;item id="1000" parentID="0" restricted="0"&gt;
            &lt;dc:title&gt;{filename_view}&lt;/dc:title&gt;
            &lt;dc:description/&gt;
            &lt;res protocolInfo="http-get:*:audio/mpeg:DLNA.ORG_OP=01"&gt;{FILE_PATH}&lt;/res&gt;
            &lt;upnp:albumArtURI&gt;{FILE_PATH_ICON}&lt;/upnp:albumArtURI&gt;
            &lt;upnp:class&gt;object.item.audioItem&lt;/upnp:class&gt;
          &lt;/item&gt;
        &lt;/DIDL-Lite&gt;
      </CurrentURIMetaData>
    </u:SetAVTransportURI>
  </s:Body>
</s:Envelope>"""

    print(f"SetAVTransportURI:  {set_uri_xml}")
    # Copia file
    file_copy = "./" + filetocopy  # Replace with the desired path for the copy
    copy_file(directory_path + "/" + filename, file_copy)
    # --- Send SOAP requests upnp ---
    send_upnp_request("urn:schemas-upnp-org:service:AVTransport:1#Stop", stop_xml)
    time.sleep(1)
    send_upnp_request("urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI", set_uri_xml)
    time.sleep(1)
    send_upnp_request("urn:schemas-upnp-org:service:AVTransport:1#Play", play_xml)
    time.sleep(20)
    send_upnp_request("urn:schemas-upnp-org:service:AVTransport:1#GetPositionInfo", PositionInfo_xml)
    time.sleep(1)
    # --- Start the GetTransportInfo loop ---
    get_transport_info_loop()
    print("End loop GetTransportInfo")

# --- Keep the main program running (now just for the web server) ---
try:
    while True:
        time.sleep(1)  # Keep the main thread alive for the web server
except KeyboardInterrupt:
    print("Keyboard break. Ending...")
    exit()
